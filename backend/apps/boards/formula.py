"""Formula columns: a small, safe expression language over an item's other columns (0007).

    {Monthly fee} * {Term}
    IF({Status} = "Live", DAYS({Ordered}, {Go-live}), "")
    ROUND({Order value} * 1.15, 2)

Column titles go in braces. Supported: numbers, "text", + - * / %, comparisons (= <> != < > <= >=),
AND/OR/NOT, and the functions in FUNCTIONS. A blank input makes arithmetic blank, as in monday.com.
Expressions are parsed with Python's `ast` and only the node types below are allowed, so a
formula can never run code. Evaluation is bounded in size and depth.
"""

import ast
import datetime as dt
import re
from decimal import Decimal, InvalidOperation

MAX_LENGTH = 1000
REFERENCE = re.compile(r"\{([^{}]{1,100})\}")


class FormulaError(ValueError):
    pass


def _num(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return None


def _date(value):
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError, TypeError:
        return None


def _if(cond, a, b=None):
    return a if cond else b


def _days(start, end):
    s, e = _date(start), _date(end)
    return None if s is None or e is None else Decimal((e - s).days)


def _many(args):
    out = []
    for a in args:
        out += a if isinstance(a, list) else [a]
    return [n for n in (_num(a) for a in out) if n is not None]


def _round(x, places=0):
    n, p = _num(x), _num(places)
    if n is None:
        return None
    return round(n, int(p or 0))


def _concat(*args):
    return "".join("" if a is None else _text(a) for a in args)


def _text(value) -> str:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value == value.to_integral() else str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


FUNCTIONS = {
    "IF": _if,
    "SUM": lambda *a: sum(_many(a), Decimal(0)),
    "AVG": lambda *a: (sum(v := _many(a)) / len(v)) if _many(a) else None,
    "MIN": lambda *a: min(_many(a), default=None),
    "MAX": lambda *a: max(_many(a), default=None),
    "ROUND": _round,
    "ABS": lambda x: None if _num(x) is None else abs(_num(x)),
    "DAYS": _days,
    "TODAY": lambda: dt.date.today(),
    "ADD_DAYS": lambda d, n: (
        None if _date(d) is None or _num(n) is None else _date(d) + dt.timedelta(days=int(_num(n)))
    ),
    "CONCAT": _concat,
    "LEN": lambda s: Decimal(len(_text(s))) if s is not None else Decimal(0),
    "UPPER": lambda s: None if s is None else _text(s).upper(),
    "LOWER": lambda s: None if s is None else _text(s).lower(),
    "BLANK": lambda x: x is None or x == "",
}

_BINARY = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Mod: lambda a, b: a % b,
}
_COMPARE = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


def compile_formula(expression: str) -> tuple[ast.Expression, list[str]]:
    """Parse once: (tree, the column titles it refers to, in variable order)."""
    if not isinstance(expression, str) or len(expression) > MAX_LENGTH:
        raise FormulaError(f"Write a formula of at most {MAX_LENGTH} characters.")
    titles: list[str] = []

    def name_of(match):
        title = match.group(1).strip()
        if title not in titles:
            titles.append(title)
        return f"__c{titles.index(title)}"

    source = REFERENCE.sub(name_of, expression)
    source = re.sub(r"(?<![<>!=])=(?!=)", "==", source).replace("<>", "!=")
    source = re.sub(r"\bAND\b", " and ", source)
    source = re.sub(r"\bOR\b", " or ", source)
    source = re.sub(r"\bNOT\b", " not ", source)
    source = re.sub(r"\bTRUE\b", "True", source)
    source = re.sub(r"\bFALSE\b", "False", source)
    try:
        tree = ast.parse(source.strip() or "None", mode="eval")
    except SyntaxError as error:
        raise FormulaError("That formula isn't written correctly.") from error
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS):
                raise FormulaError("Use only the functions in the list.")
            if node.keywords:
                raise FormulaError("Functions take plain values.")
        elif isinstance(node, ast.Name):
            if not (node.id.startswith("__c") or node.id in FUNCTIONS):
                raise FormulaError(f"Unknown name {node.id!r}: put column titles in braces.")
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float, str, bool, type(None))):
                raise FormulaError("Unsupported value.")
            if isinstance(node.value, str) and len(node.value) > 500:
                raise FormulaError("Text in a formula is limited to 500 characters.")
        elif isinstance(node, ast.BinOp):
            if type(node.op) not in _BINARY:
                raise FormulaError("Use + - * / or %.")
        elif isinstance(node, ast.Compare):
            if any(type(op) not in _COMPARE for op in node.ops):
                raise FormulaError("Use = <> < > <= or >=.")
        elif not isinstance(
            node,
            (
                ast.Expression,
                ast.UnaryOp,
                ast.USub,
                ast.UAdd,
                ast.Not,
                ast.BoolOp,
                ast.And,
                ast.Or,
                ast.Load,
                ast.Eq,
                ast.NotEq,
                ast.Lt,
                ast.LtE,
                ast.Gt,
                ast.GtE,
                *(_BINARY.keys()),
            ),
        ):
            raise FormulaError("That formula uses something that isn't supported.")
    return tree, titles


def evaluate(tree: ast.Expression, variables: list):
    """The formula's value, or None (blank) when an input is blank or the maths fails."""

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            v = node.value
            return Decimal(str(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
        if isinstance(node, ast.Name):
            if node.id.startswith("__c"):
                return variables[int(node.id[3:])]
            raise FormulaError(node.id)
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            if isinstance(node.op, ast.Not):
                return not v
            n = _num(v)
            return None if n is None else (-n if isinstance(node.op, ast.USub) else n)
        if isinstance(node, ast.BoolOp):
            values = [ev(v) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add) and (isinstance(a, str) or isinstance(b, str)):
                return _concat(a, b)
            if isinstance(a, dt.date) and isinstance(node.op, (ast.Add, ast.Sub)):
                n = _num(b)
                if isinstance(b, dt.date) and isinstance(node.op, ast.Sub):
                    return Decimal((a - b).days)
                if n is None:
                    return None
                days = dt.timedelta(days=int(n))
                return a + days if isinstance(node.op, ast.Add) else a - days
            x, y = _num(a), _num(b)
            if x is None or y is None:
                return None
            return _BINARY[type(node.op)](x, y)
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, right_node in zip(node.ops, node.comparators, strict=True):
                right = ev(right_node)
                a, b = _comparable(left, right)
                try:
                    if not _COMPARE[type(op)](a, b):
                        return False
                except TypeError:
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            return FUNCTIONS[node.func.id](*(ev(a) for a in node.args))
        raise FormulaError("Unsupported")

    try:
        return ev(tree)
    except ArithmeticError, InvalidOperation, TypeError, ValueError, OverflowError:
        return None


def _comparable(a, b):
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None and not isinstance(a, str) and not isinstance(b, str):
        return na, nb
    if isinstance(a, dt.date) or isinstance(b, dt.date):
        return _date(a), _date(b)
    if na is not None and nb is not None:
        return na, nb
    return ("" if a is None else _text(a)).lower(), ("" if b is None else _text(b)).lower()


def as_value(result):
    """A formula result as JSON: numbers as strings (exact), dates ISO, text and booleans as
    they are."""
    if result is None:
        return None
    if isinstance(result, Decimal):
        if not result.is_finite():
            return None
        q = result.quantize(Decimal("0.0001")) if result.as_tuple().exponent < -4 else result
        return _text(q.normalize() if q == q.to_integral() else q)
    if isinstance(result, dt.date):
        return result.isoformat()
    if isinstance(result, bool):
        return result
    return str(result)[:2000]
