// Source: ivendnext/partner-programme spikes/wasm/tools/meter/src/main.rs @ 2799842dca46, vendored: its one home is there. A defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository).
//! pp_meter — DETERMINISTIC METERING written into the module itself (from the WebAssembly spike's metering-gap prototype).
//!
//! A browser has no fuel counter and the server's wasmtime fuel counts differently from any timeout, so the same
//! input can trap on one host and finish on the other (VERDICT §metering). This tool removes the possibility rather
//! than testing for it: it adds ONE exported mutable global, `pp_fuel` (i64), and at the start of EVERY instruction
//! sequence of every function (each function body, block, loop body and if-arm) it subtracts that sequence's own
//! instruction count and traps when the counter goes below zero. A loop charges on every iteration and a call on
//! every entry, so nothing runs unbounded. Both hosts set `pp_fuel` before the call and read it after; the counter
//! lives in the module's own code, so it reaches zero at the SAME instruction on every engine.
//! The charge is per BASIC BLOCK, not per sequence: a sequence is cut after every nested block, loop or if (a branch
//! out of it lands just after it) and after every branch, and each piece is charged on entry for its own length.
//! (Measured: charging a whole sequence on entry over-charged an interpreter's dispatch ~50x — every opcode paid for
//! every case body inlined in the same sequence.)
//! The trap is a deliberate `1 / 0` (no new blocks needed); a host names any trap with `pp_fuel < 0` out_of_fuel.
//! A bulk `memory.fill` / `memory.copy` is ONE instruction whatever its length, so each also pays its length / 64 at
//! run time (review finding 1; measured: a loop of 9 MiB fills ran ~20 s past a Worker's termination).
//!
//!     pp_meter <in.wasm> <out.wasm>
use walrus::ir::{BinaryOp, Binop, Const, Drop, GlobalGet, GlobalSet, Instr, InstrLocId, InstrSeq, InstrSeqId, Unop, UnaryOp, Value, Visitor};
use walrus::ir::{LocalGet, LocalTee};
use walrus::{ConstExpr, GlobalId, LocalId, Module, ValType};

struct Seqs(Vec<InstrSeqId>);
impl<'a> Visitor<'a> for Seqs {
    fn start_instr_seq(&mut self, seq: &'a InstrSeq) {
        self.0.push(seq.id());
    }
}

fn charge(fuel: GlobalId, cost: i64) -> Vec<(Instr, InstrLocId)> {
    let at = InstrLocId::default();
    vec![
        // pp_fuel -= cost
        (Instr::GlobalGet(GlobalGet { global: fuel }), at),
        (Instr::Const(Const { value: Value::I64(cost) }), at),
        (Instr::Binop(Binop { op: BinaryOp::I64Sub }), at),
        (Instr::GlobalSet(GlobalSet { global: fuel }), at),
        // trap when pp_fuel < 0: 1 / (sign bit == 0) divides by zero exactly when the counter is negative
        (Instr::Const(Const { value: Value::I32(1) }), at),
        (Instr::GlobalGet(GlobalGet { global: fuel }), at),
        (Instr::Const(Const { value: Value::I64(63) }), at),
        (Instr::Binop(Binop { op: BinaryOp::I64ShrU }), at),
        (Instr::Unop(Unop { op: UnaryOp::I32WrapI64 }), at),
        (Instr::Unop(Unop { op: UnaryOp::I32Eqz }), at),
        (Instr::Binop(Binop { op: BinaryOp::I32DivU }), at),
        (Instr::Drop(Drop {}), at),
    ]
}

/// Before a memory.fill / memory.copy, with its length on top of the stack: keep the length (local.tee), charge
/// length / 64 to the counter, trap when it goes negative, and leave the stack as it was.
fn charge_length(fuel: GlobalId, len: LocalId) -> Vec<(Instr, InstrLocId)> {
    let at = InstrLocId::default();
    let mut v = vec![
        (Instr::LocalTee(LocalTee { local: len }), at),
        (Instr::GlobalGet(GlobalGet { global: fuel }), at),
        (Instr::LocalGet(LocalGet { local: len }), at),
        (Instr::Unop(Unop { op: UnaryOp::I64ExtendUI32 }), at),
        (Instr::Const(Const { value: Value::I64(6) }), at),
        (Instr::Binop(Binop { op: BinaryOp::I64ShrU }), at),
        (Instr::Binop(Binop { op: BinaryOp::I64Sub }), at),
        (Instr::GlobalSet(GlobalSet { global: fuel }), at),
    ];
    v.extend(charge(fuel, 0).into_iter().skip(4)); // the trap test alone (charge()'s first four lines subtract)
    v
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let (src, dst) = (&args[1], &args[2]);
    let mut module = Module::from_file(src).expect("parse the module");
    let fuel = module.globals.add_local(ValType::I64, true, false, ConstExpr::Value(Value::I64(0)));
    module.exports.add("pp_fuel", fuel);
    let len_local = module.locals.add(ValType::I32); // holds a bulk op's length while it is charged
    let (mut funcs, mut seqs_total) = (0usize, 0usize);
    for (_, func) in module.funcs.iter_local_mut() {
        let mut seqs = Seqs(Vec::new());
        walrus::ir::dfs_in_order(&mut seqs, func, func.entry_block());
        for id in seqs.0 {
            let seq = func.block_mut(id);
            let old = std::mem::take(&mut seq.instrs);
            let mut cuts = Vec::new(); // the length of each basic block in this sequence
            let mut len = 0usize;
            for (ins, _) in &old {
                len += 1;
                if matches!(ins, Instr::Block(_) | Instr::Loop(_) | Instr::IfElse(_) | Instr::Br(_) | Instr::BrIf(_)
                    | Instr::BrTable(_) | Instr::Return(_) | Instr::Unreachable(_)) {
                    cuts.push(len);
                    len = 0;
                }
            }
            if len > 0 || cuts.is_empty() {
                cuts.push(len.max(1)); // an empty sequence still charges 1: every entry costs something
            }
            let mut rest = old.into_iter();
            let mut instrs = Vec::new();
            for c in cuts {
                instrs.extend(charge(fuel, c as i64));
                for item in rest.by_ref().take(c) {
                    if matches!(item.0, Instr::MemoryFill(_) | Instr::MemoryCopy(_)) {
                        instrs.extend(charge_length(fuel, len_local));
                    }
                    instrs.push(item);
                }
                seqs_total += 1;
            }
            seq.instrs = instrs;
        }
        funcs += 1;
    }
    module.emit_wasm_file(dst).expect("write the module");
    eprintln!("metered {src} -> {dst}: {funcs} functions, {seqs_total} basic blocks charged");
}
