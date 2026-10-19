//! The kit's JSON, integer-only. ⛔ Do not edit. Reads exactly what the host contract allows (CONTRACT §2): objects,
//! arrays, strings, `null`, `true`/`false`, and non-negative integers. Any other number (a sign, a fraction, an exponent,
//! more than 19 digits) is read as `Num::Other`, so a field check refuses it at its own path — as the first spike's builds did.
//! Writes the contract's canonical form (§4): no spaces; `\" \\ \b \f \n \r \t`; other control characters as `\u00xx`.

#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Int(i64),
    OtherNumber,
    Str(String),
    Arr(Vec<Value>),
    Obj(Vec<(String, Value)>),
}

impl Value {
    /// A key's value; a key repeated in one object keeps its LAST value (CONTRACT §3).
    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Obj(kv) => kv.iter().rev().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }
}

pub fn s(x: &str) -> Value {
    Value::Str(x.to_string())
}

pub fn obj(kv: Vec<(&str, Value)>) -> Value {
    Value::Obj(kv.into_iter().map(|(k, v)| (k.to_string(), v)).collect())
}

const MAX_DEPTH: usize = 128; // deeper input is refused as "input" (as serde_json did in the first spike); the contract allows 32

struct P<'a> {
    b: &'a [u8],
    i: usize,
}

pub fn parse(input: &[u8]) -> Result<Value, ()> {
    if core::str::from_utf8(input).is_err() {
        return Err(());
    }
    let mut p = P { b: input, i: 0 };
    let v = p.value(0)?;
    p.ws();
    if p.i == p.b.len() { Ok(v) } else { Err(()) }
}

impl<'a> P<'a> {
    fn ws(&mut self) {
        while self.i < self.b.len() && matches!(self.b[self.i], b' ' | b'\t' | b'\n' | b'\r') {
            self.i += 1;
        }
    }
    fn eat(&mut self, c: u8) -> Result<(), ()> {
        self.ws();
        if self.b.get(self.i) == Some(&c) { self.i += 1; Ok(()) } else { Err(()) }
    }
    fn lit(&mut self, word: &[u8], v: Value) -> Result<Value, ()> {
        if self.b[self.i..].starts_with(word) { self.i += word.len(); Ok(v) } else { Err(()) }
    }
    fn value(&mut self, depth: usize) -> Result<Value, ()> {
        if depth > MAX_DEPTH {
            return Err(());
        }
        self.ws();
        match self.b.get(self.i).copied().ok_or(())? {
            b'{' => {
                self.i += 1;
                let mut kv = Vec::new();
                self.ws();
                if self.b.get(self.i) == Some(&b'}') { self.i += 1; return Ok(Value::Obj(kv)); }
                loop {
                    self.ws();
                    let k = self.string()?;
                    self.eat(b':')?;
                    kv.push((k, self.value(depth + 1)?));
                    self.ws();
                    match self.b.get(self.i) {
                        Some(b',') => self.i += 1,
                        Some(b'}') => { self.i += 1; return Ok(Value::Obj(kv)); }
                        _ => return Err(()),
                    }
                }
            }
            b'[' => {
                self.i += 1;
                let mut a = Vec::new();
                self.ws();
                if self.b.get(self.i) == Some(&b']') { self.i += 1; return Ok(Value::Arr(a)); }
                loop {
                    a.push(self.value(depth + 1)?);
                    self.ws();
                    match self.b.get(self.i) {
                        Some(b',') => self.i += 1,
                        Some(b']') => { self.i += 1; return Ok(Value::Arr(a)); }
                        _ => return Err(()),
                    }
                }
            }
            b'"' => Ok(Value::Str(self.string()?)),
            b'n' => self.lit(b"null", Value::Null),
            b't' => self.lit(b"true", Value::Bool(true)),
            b'f' => self.lit(b"false", Value::Bool(false)),
            b'-' | b'0'..=b'9' => self.number(),
            _ => Err(()),
        }
    }
    fn number(&mut self) -> Result<Value, ()> {
        let start = self.i;
        if self.b[self.i] == b'-' { self.i += 1; }
        let digits = self.i;
        while self.i < self.b.len() && self.b[self.i].is_ascii_digit() { self.i += 1; }
        if self.i == digits || (self.b[digits] == b'0' && self.i - digits > 1) {
            return Err(()); // no digits, or a leading zero: not JSON
        }
        let mut plain = start == digits;
        if self.b.get(self.i) == Some(&b'.') {
            self.i += 1;
            let f = self.i;
            while self.i < self.b.len() && self.b[self.i].is_ascii_digit() { self.i += 1; }
            if self.i == f { return Err(()); }
            plain = false;
        }
        if matches!(self.b.get(self.i), Some(b'e') | Some(b'E')) {
            self.i += 1;
            if matches!(self.b.get(self.i), Some(b'+') | Some(b'-')) { self.i += 1; }
            let e = self.i;
            while self.i < self.b.len() && self.b[self.i].is_ascii_digit() { self.i += 1; }
            if self.i == e { return Err(()); }
            plain = false;
        }
        if !plain || self.i - digits > 18 {
            // a sign, a fraction, an exponent, or 19+ digits: a number, but not one this contract reads as an integer
            // (every integer the contract allows has at most 13 digits)
            return Ok(Value::OtherNumber);
        }
        let mut n: i64 = 0;
        for &c in &self.b[digits..self.i] { n = n * 10 + (c - b'0') as i64; }
        Ok(Value::Int(n))
    }
    fn hex4(&mut self) -> Result<u32, ()> {
        let h = self.b.get(self.i..self.i + 4).ok_or(())?;
        self.i += 4;
        let mut n = 0u32;
        for &c in h {
            n = n * 16 + (c as char).to_digit(16).ok_or(())?;
        }
        Ok(n)
    }
    fn string(&mut self) -> Result<String, ()> {
        if self.b.get(self.i) != Some(&b'"') { return Err(()); }
        self.i += 1;
        let mut out: Vec<u8> = Vec::new();
        loop {
            let c = *self.b.get(self.i).ok_or(())?;
            self.i += 1;
            match c {
                b'"' => return String::from_utf8(out).map_err(|_| ()),
                b'\\' => {
                    let e = *self.b.get(self.i).ok_or(())?;
                    self.i += 1;
                    let ch = match e {
                        b'"' => '"', b'\\' => '\\', b'/' => '/', b'b' => '\u{8}', b'f' => '\u{c}',
                        b'n' => '\n', b'r' => '\r', b't' => '\t',
                        b'u' => {
                            let hi = self.hex4()?;
                            let cp = if (0xD800..0xDC00).contains(&hi) {
                                if self.b.get(self.i..self.i + 2) != Some(b"\\u") { return Err(()); }
                                self.i += 2;
                                let lo = self.hex4()?;
                                if !(0xDC00..0xE000).contains(&lo) { return Err(()); }
                                0x10000 + ((hi - 0xD800) << 10) + (lo - 0xDC00)
                            } else if (0xDC00..0xE000).contains(&hi) {
                                return Err(()); // a lone low surrogate: outside the contract
                            } else {
                                hi
                            };
                            char::from_u32(cp).ok_or(())?
                        }
                        _ => return Err(()),
                    };
                    let mut buf = [0u8; 4];
                    out.extend_from_slice(ch.encode_utf8(&mut buf).as_bytes());
                }
                0x00..=0x1F => return Err(()), // a raw control character is not JSON
                _ => out.push(c),
            }
        }
    }
}

pub fn write(v: &Value) -> String {
    let mut o = String::new();
    put(v, &mut o);
    o
}

fn put(v: &Value, o: &mut String) {
    match v {
        Value::Null => o.push_str("null"),
        Value::Bool(b) => o.push_str(if *b { "true" } else { "false" }),
        Value::Int(n) => o.push_str(&n.to_string()),
        Value::OtherNumber => o.push_str("null"), // never written by a point: it only ever reads one
        Value::Str(s) => quote(s, o),
        Value::Arr(a) => {
            o.push('[');
            for (i, x) in a.iter().enumerate() {
                if i > 0 { o.push(','); }
                put(x, o);
            }
            o.push(']');
        }
        Value::Obj(kv) => {
            o.push('{');
            for (i, (k, x)) in kv.iter().enumerate() {
                if i > 0 { o.push(','); }
                quote(k, o);
                o.push(':');
                put(x, o);
            }
            o.push('}');
        }
    }
}

fn quote(s: &str, o: &mut String) {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    o.push('"');
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""), '\\' => o.push_str("\\\\"), '\u{8}' => o.push_str("\\b"),
            '\u{c}' => o.push_str("\\f"), '\n' => o.push_str("\\n"), '\r' => o.push_str("\\r"),
            '\t' => o.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                o.push_str("\\u00");
                o.push(HEX[(c as usize) >> 4] as char);
                o.push(HEX[(c as usize) & 15] as char);
            }
            c => o.push(c),
        }
    }
    o.push('"');
}
