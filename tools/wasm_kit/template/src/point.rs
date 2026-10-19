//! YOUR POINT — the one file you edit. `decide` gets the host's input (already parsed) and returns the answer, or the
//! path of the first field that fails validation (the host turns it into `{"error":"invalid_input","at":…}`).
//!
//! Rules a point lives by (tools/wasm_kit/CONTRACT.md):
//!   * money is integer minor units, quantity integer thousandths; no float anywhere (the kit's admission refuses one);
//!   * the same input always gives the same answer: no clock, no randomness, no state between calls;
//!   * validate in the published order and name the FIRST failing path;
//!   * stay far inside the budgets: fuel 11 000 000 units, stack 10 000 units, memory 10 MiB, answer 512 KiB.
//!
//! The worked example below is a `price/1` module (P-PRICE, *pricing condition and adjuster*): a member discount taken
//! AFTER the promotions, on the promotion-adjusted line. It is the POS app's own test module, copied from
//! ivendnext/iVendNext_PWA apps/ivendnext_mpos/ivendnext_mpos/tests/wasm_modules/price_member/point.rs @ fa6f1597e
//! (2026-10-12), which was itself built from this template. A defect here is a defect there — report it on the
//! Partner Programme's board.
//!
//! In (`price/1`): `{v, customer_group, currency, currency_exponent, lines:[{luid, item, item_group, qty_milli,
//! unit_price_minor, line_total_minor, promotion_discount_minor}], config:{rules:[{id, item_group, customer_group,
//! percent_bp, cap_minor, min_qty_milli}]}}` — money in minor units, quantity in thousandths, no negative number.
//! A rule's `item_group` or `customer_group` `"*"` matches any; a `null` sale group matches only `"*"`.
//! Out: `[{luid, discount_minor, reason}]` — per line the best rule's cut, `floor(base × percent_bp / 10000)` where the
//! base is `line_total_minor − promotion_discount_minor`, capped at `cap_minor` and at the base; a tie goes to the
//! earliest rule; a line whose best cut is 0 gets no entry; `reason` is the winning rule's `id`. A context it cannot
//! read is `{"error":"invalid_input","at":…}`, which the POS refuses whole (no adjustment, a flagged log row).

use crate::json::{obj, s, Value};

const MAX_SAFE: i64 = 9_007_199_254_740_991; // 2^53 - 1
const QTY_MAX: i64 = 1_000_000_000_000;

fn string(o: &Value, key: &str, at: &str, min: usize, max: usize) -> Result<String, String> {
    match o.get(key) {
        Some(Value::Str(x)) if x.len() >= min && x.len() <= max => Ok(x.clone()),
        _ => Err(format!("{at}.{key}")),
    }
}

fn int(o: &Value, key: &str, at: &str, min: i64, max: i64) -> Result<i64, String> {
    match o.get(key) {
        Some(Value::Int(n)) if *n >= min && *n <= max => Ok(*n),
        _ => Err(format!("{at}.{key}")),
    }
}

struct Line { luid: String, item_group: String, qty_milli: i64, base: i64 }
struct Rule { id: String, item_group: String, customer_group: String, percent_bp: i64, cap_minor: Option<i64>,
              min_qty_milli: i64 }

pub fn decide(input: &Value) -> Result<Value, String> {
    if !matches!(input, Value::Obj(_)) {
        return Err("input".into());
    }
    int(input, "v", "input", 1, 1).map_err(|_| "v".to_string())?;
    let customer_group = match input.get("customer_group") {
        Some(Value::Null) => None,
        Some(Value::Str(x)) if x.len() <= 140 => Some(x.clone()),
        _ => return Err("customer_group".into()),
    };
    string(input, "currency", "input", 0, 140).map_err(|_| "currency".to_string())?;
    int(input, "currency_exponent", "input", 0, 4).map_err(|_| "currency_exponent".to_string())?;
    let raw_lines = match input.get("lines") {
        Some(Value::Arr(a)) if a.len() <= 500 => a,
        _ => return Err("lines".into()),
    };
    let mut lines: Vec<Line> = Vec::with_capacity(raw_lines.len());
    for (i, o) in raw_lines.iter().enumerate() {
        let at = format!("lines[{i}]");
        if !matches!(o, Value::Obj(_)) {
            return Err(at);
        }
        let luid = string(o, "luid", &at, 1, 80)?;
        string(o, "item", &at, 0, 140)?;
        let item_group = string(o, "item_group", &at, 0, 140)?;
        let qty_milli = int(o, "qty_milli", &at, 1, QTY_MAX)?;
        int(o, "unit_price_minor", &at, 0, MAX_SAFE)?;
        let line_total_minor = int(o, "line_total_minor", &at, 0, MAX_SAFE)?;
        let promotion = int(o, "promotion_discount_minor", &at, 0, line_total_minor)?;
        if lines.iter().any(|l| l.luid == luid) {
            return Err(format!("{at}.luid"));
        }
        lines.push(Line { luid, item_group, qty_milli, base: line_total_minor - promotion });
    }
    let config = match input.get("config") {
        Some(c @ Value::Obj(_)) => c,
        _ => return Err("config".into()),
    };
    let raw_rules = match config.get("rules") {
        Some(Value::Arr(a)) if a.len() <= 100 => a,
        _ => return Err("config.rules".into()),
    };
    let mut rules = Vec::with_capacity(raw_rules.len());
    for (j, o) in raw_rules.iter().enumerate() {
        let at = format!("config.rules[{j}]");
        if !matches!(o, Value::Obj(_)) {
            return Err(at);
        }
        let id = string(o, "id", &at, 1, 40)?;
        let item_group = string(o, "item_group", &at, 0, 140)?;
        let customer_group = string(o, "customer_group", &at, 0, 140)?;
        let percent_bp = int(o, "percent_bp", &at, 0, 10_000)?;
        let cap_minor = match o.get("cap_minor") {
            Some(Value::Null) => None,
            _ => Some(int(o, "cap_minor", &at, 0, MAX_SAFE)?),
        };
        let min_qty_milli = int(o, "min_qty_milli", &at, 0, QTY_MAX)?;
        rules.push(Rule { id, item_group, customer_group, percent_bp, cap_minor, min_qty_milli });
    }
    let mut out = Vec::new();
    for line in &lines {
        let mut best: Option<(i64, &str)> = None;
        for r in &rules {
            let group_ok = r.customer_group == "*" || Some(&r.customer_group) == customer_group.as_ref();
            let item_ok = r.item_group == "*" || r.item_group == line.item_group;
            if !item_ok || !group_ok || line.qty_milli < r.min_qty_milli {
                continue;
            }
            // the exact product, in i128: it can pass i64 (CONTRACT §1)
            let raw = (line.base as i128 * r.percent_bp as i128 / 10_000) as i64;
            let d = r.cap_minor.map_or(raw, |c| raw.min(c)).min(line.base);
            if best.map_or(true, |(b, _)| d > b) {
                best = Some((d, &r.id));
            }
        }
        if let Some((d, id)) = best {
            if d > 0 {
                out.push(obj(vec![("luid", s(&line.luid)), ("discount_minor", Value::Int(d)), ("reason", s(id))]));
            }
        }
    }
    Ok(Value::Arr(out))
}

#[cfg(test)]
mod tests {
    fn run(x: &str) -> String {
        String::from_utf8(crate::answer(x.as_bytes())).unwrap()
    }

    const HEAD: &str = r#""v":1,"currency":"AED","currency_exponent":2"#;

    #[test]
    fn s1_five_percent_of_the_promotion_adjusted_line() {
        // spec §10 S1: a 100.00 line with a 10.00 promotion, a 5 % member rule ⇒ 450 (5 % of 90.00)
        let input = format!(
            r#"{{{HEAD},"customer_group":"Select","lines":[
            {{"luid":"0.0","item":"X","item_group":"Products","qty_milli":1000,"unit_price_minor":9000,
              "line_total_minor":10000,"promotion_discount_minor":1000}}],
            "config":{{"rules":[{{"id":"Select 5%","item_group":"*","customer_group":"Select","percent_bp":500,
              "cap_minor":null,"min_qty_milli":0}}]}}}}"#
        );
        assert_eq!(run(&input), r#"[{"luid":"0.0","discount_minor":450,"reason":"Select 5%"}]"#);
    }

    #[test]
    fn another_group_and_a_null_group_take_nothing() {
        let line = r#"{"luid":"a","item":"X","item_group":"G","qty_milli":1000,"unit_price_minor":100,
            "line_total_minor":100,"promotion_discount_minor":0}"#;
        let rules = r#"{"rules":[{"id":"R","item_group":"G","customer_group":"Select","percent_bp":500,
            "cap_minor":null,"min_qty_milli":0}]}"#;
        assert_eq!(run(&format!(r#"{{{HEAD},"customer_group":"Gold","lines":[{line}],"config":{rules}}}"#)), "[]");
        assert_eq!(run(&format!(r#"{{{HEAD},"customer_group":null,"lines":[{line}],"config":{rules}}}"#)), "[]");
    }

    #[test]
    fn refusals_name_the_first_failing_path() {
        assert_eq!(run("[]"), r#"{"error":"invalid_input","at":"input"}"#);
        assert_eq!(run(r#"{"v":2}"#), r#"{"error":"invalid_input","at":"v"}"#);
        // a promotion above its line is outside the contract
        let over = format!(
            r#"{{{HEAD},"customer_group":null,"lines":[{{"luid":"a","item":"X","item_group":"G","qty_milli":1000,
            "unit_price_minor":1,"line_total_minor":1,"promotion_discount_minor":2}}],"config":{{"rules":[]}}}}"#
        );
        assert_eq!(run(&over), r#"{"error":"invalid_input","at":"lines[0].promotion_discount_minor"}"#);
    }
}
