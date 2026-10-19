//! pp_stackmeter — the kit's DETERMINISTIC STACK BOUND, written into the module itself (the first spike
//! left it unbuilt). Run at publish, BEFORE the fuel meter (`meter/`).
//!
//! An engine's call stack is its own size and moves with warm-up (measured: the server overflows at 10 000 levels,
//! Chrome at 8 000, Node cold at 50 000 and warm past 62 500), so a deep enough call chain could finish on one host and
//! trap on another. This tool removes that possibility the way the fuel meter does for loops: one module-local global,
//! `pp_stack` (i32), counts the frames in use. Every function, on entry, adds its own frame cost — its parameters + its
//! locals + 4 — and traps when the count passes the bound; on every way out it subtracts it again. The count lives in
//! the module, so it trips at the SAME call on every engine — AS LONG AS IT TRIPS BEFORE ANY ENGINE'S OWN STACK RUNS
//! OUT. The bound (10 000 units by default) allows at most 2 500 of the smallest frames, against the smallest stack
//! measured (Chrome: 5 000 passing levels of a one-parameter function). ⚠ BOUND (found in review): the unit cost counts
//! parameters and locals, not operand-stack depth or a compiler's spills, so a function whose native frame is far larger
//! than its locals suggest could exhaust an engine's stack first. Measured only for one recursion module;
//! other shapes are UNPROVEN.
//!
//! The trap is `i32.div_s(INT_MIN, -1)`: both hosts name it `integer_overflow`, which no Rust code reaches by itself
//! (Rust checks a signed division and panics instead). Ways out handled: falling off the end, `return`, and a branch to
//! the function's own label (rewritten to an inner block, so it also runs the subtraction). Tail calls are refused
//! earlier by the kit's scan.
//!
//!     pp_stackmeter <in.wasm> <out.wasm> [bound]
use std::collections::HashSet;
use walrus::ir::{BinaryOp, Binop, Block, Const, Drop, GlobalGet, GlobalSet, Instr, InstrLocId, InstrSeq, InstrSeqId,
                 InstrSeqType, Value, Visitor};
use walrus::{ConstExpr, FunctionKind, LocalId, Module, ValType};

struct Seqs(Vec<InstrSeqId>);
impl<'a> Visitor<'a> for Seqs {
    fn start_instr_seq(&mut self, seq: &'a InstrSeq) {
        self.0.push(seq.id());
    }
}

struct Locals(HashSet<LocalId>);
impl<'a> Visitor<'a> for Locals {
    fn visit_local_id(&mut self, l: &LocalId) {
        self.0.insert(*l);
    }
}

fn at() -> InstrLocId {
    InstrLocId::default()
}

fn enter(g: walrus::GlobalId, cost: i32, bound: i32) -> Vec<(Instr, InstrLocId)> {
    vec![
        // pp_stack += cost
        (Instr::GlobalGet(GlobalGet { global: g }), at()),
        (Instr::Const(Const { value: Value::I32(cost) }), at()),
        (Instr::Binop(Binop { op: BinaryOp::I32Add }), at()),
        (Instr::GlobalSet(GlobalSet { global: g }), at()),
        // INT_MIN / (1 - 2 * (pp_stack > bound)): divides by -1, and traps integer_overflow, exactly past the bound
        (Instr::Const(Const { value: Value::I32(i32::MIN) }), at()),
        (Instr::Const(Const { value: Value::I32(1) }), at()),
        (Instr::GlobalGet(GlobalGet { global: g }), at()),
        (Instr::Const(Const { value: Value::I32(bound) }), at()),
        (Instr::Binop(Binop { op: BinaryOp::I32GtS }), at()),
        (Instr::Const(Const { value: Value::I32(1) }), at()),
        (Instr::Binop(Binop { op: BinaryOp::I32Shl }), at()),
        (Instr::Binop(Binop { op: BinaryOp::I32Sub }), at()),
        (Instr::Binop(Binop { op: BinaryOp::I32DivS }), at()),
        (Instr::Drop(Drop {}), at()),
    ]
}

fn leave(g: walrus::GlobalId, cost: i32) -> Vec<(Instr, InstrLocId)> {
    vec![
        (Instr::GlobalGet(GlobalGet { global: g }), at()),
        (Instr::Const(Const { value: Value::I32(cost) }), at()),
        (Instr::Binop(Binop { op: BinaryOp::I32Sub }), at()),
        (Instr::GlobalSet(GlobalSet { global: g }), at()),
    ]
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let (src, dst) = (&args[1], &args[2]);
    let bound: i32 = args.get(3).map(|b| b.parse().expect("bound")).unwrap_or(10_000);
    let mut module = Module::from_file(src).expect("parse the module");
    let g = module.globals.add_local(ValType::I32, true, false, ConstExpr::Value(Value::I32(0)));
    let funcs: Vec<_> = module.funcs.iter_local().map(|(id, f)| (id, f.ty())).collect();
    let (mut n, mut max_cost) = (0usize, 0i32);
    for (fid, ty) in funcs {
        let (params, results) = {
            let t = module.types.get(ty);
            (t.params().len(), t.results().to_vec())
        };
        let seq_ty = InstrSeqType::new(&mut module.types, &[], &results);
        let lf = match &mut module.funcs.get_mut(fid).kind {
            FunctionKind::Local(lf) => lf,
            _ => continue,
        };
        let entry = lf.entry_block();
        let mut used = Locals(HashSet::new());
        walrus::ir::dfs_in_order(&mut used, lf, entry);
        let args: HashSet<LocalId> = lf.args.iter().copied().collect();
        let cost = (params + used.0.difference(&args).count() + 4) as i32;
        max_cost = max_cost.max(cost);
        // the body moves into an inner block; the entry block becomes: enter, the body, leave
        let inner = lf.builder_mut().dangling_instr_seq(seq_ty).id();
        let body = std::mem::take(&mut lf.block_mut(entry).instrs);
        lf.block_mut(inner).instrs = body;
        let mut seqs = Seqs(Vec::new());
        walrus::ir::dfs_in_order(&mut seqs, lf, inner);
        for id in seqs.0 {
            let old = std::mem::take(&mut lf.block_mut(id).instrs);
            let mut new = Vec::with_capacity(old.len());
            for (mut ins, loc) in old {
                match &mut ins {
                    Instr::Br(b) if b.block == entry => b.block = inner,
                    Instr::BrIf(b) if b.block == entry => b.block = inner,
                    Instr::BrTable(b) => {
                        for t in b.blocks.iter_mut() {
                            if *t == entry { *t = inner; }
                        }
                        if b.default == entry { b.default = inner; }
                    }
                    Instr::Return(_) => new.extend(leave(g, cost)),
                    _ => {}
                }
                new.push((ins, loc));
            }
            lf.block_mut(id).instrs = new;
        }
        let mut e = enter(g, cost, bound);
        e.push((Instr::Block(Block { seq: inner }), at()));
        e.extend(leave(g, cost));
        lf.block_mut(entry).instrs = e;
        n += 1;
    }
    module.emit_wasm_file(dst).expect("write the module");
    eprintln!("stack-metered {src} -> {dst}: {n} functions, bound {bound} units, largest frame {max_cost} units");
}
