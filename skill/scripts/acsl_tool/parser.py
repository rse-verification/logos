"""Parse C source files into function spans for deterministic contract insertion."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path
import re
import sys

from .models import FunctionDef


class CXIndex(ctypes.Structure):
    pass


class CXTranslationUnit(ctypes.Structure):
    pass


class CXCursor(ctypes.Structure):
    _fields_ = [
        ("kind", ctypes.c_int),
        ("xdata", ctypes.c_int),
        ("data", ctypes.c_void_p * 3),
    ]


class CXType(ctypes.Structure):
    _fields_ = [
        ("kind", ctypes.c_int),
        ("data", ctypes.c_void_p * 2),
    ]


class CXString(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p),
        ("private_flags", ctypes.c_uint),
    ]


class CXSourceLocation(ctypes.Structure):
    _fields_ = [
        ("ptr_data", ctypes.c_void_p * 2),
        ("int_data", ctypes.c_uint),
    ]


class CXSourceRange(ctypes.Structure):
    _fields_ = [
        ("ptr_data", ctypes.c_void_p * 2),
        ("begin_int_data", ctypes.c_uint),
        ("end_int_data", ctypes.c_uint),
    ]


class CXUnsavedFile(ctypes.Structure):
    _fields_ = [
        ("Filename", ctypes.c_char_p),
        ("Contents", ctypes.c_char_p),
        ("Length", ctypes.c_ulong),
    ]


CXCursorVisitor = ctypes.CFUNCTYPE(ctypes.c_uint, CXCursor, CXCursor, ctypes.c_void_p)

_LIBCLANG: ctypes.CDLL | None = None
_LIBCLANG_LOAD_ATTEMPTED = False
_LIBCLANG_ERROR = (
    "LOGOS could not load the required libclang shared library. "
    "Install Xcode Command Line Tools (`xcode-select --install`) or Homebrew LLVM "
    "(`brew install llvm`) on macOS, `sudo apt install libclang-dev` on Debian/Ubuntu, "
    "or the LLVM installer (`winget install --id LLVM.LLVM --exact`) on Windows. "
    "If already installed, set LIBCLANG_FILE to the full path of libclang.dylib, libclang.so, or libclang.dll "
    "and retry in a new process. Check that it matches your Python architecture. "
    "The clang executable alone is not sufficient. See README.md: Requirements."
)
_WINDOWS_LIBCLANG_CANDIDATES = (
    str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "LLVM" / "bin" / "libclang.dll"),
    ctypes.util.find_library("libclang"),
) if sys.platform == "win32" else ()
_LIBCLANG_CANDIDATES = (
    *_WINDOWS_LIBCLANG_CANDIDATES,
    ctypes.util.find_library("clang"),
    *(str(path) for path in sorted(Path("/usr/lib").glob("llvm-*/lib/libclang.so"))),
    "/Library/Developer/CommandLineTools/usr/lib/libclang.dylib",
    "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/libclang.dylib",
    "/opt/homebrew/opt/llvm/lib/libclang.dylib",
    "/usr/local/opt/llvm/lib/libclang.dylib",
    "libclang.so",
    "libclang-19.so.19",
    "libclang-19.so",
    "libclang-18.so.18",
    "libclang-18.so",
    "libclang-16.so.16.0.6",
    "libclang-16.so",
    "/lib/x86_64-linux-gnu/libclang-19.so.19",
    "/lib/x86_64-linux-gnu/libclang-19.so",
    "/lib/x86_64-linux-gnu/libclang-18.so.18",
    "/lib/x86_64-linux-gnu/libclang-18.so",
    "/lib/x86_64-linux-gnu/libclang-16.so.16.0.6",
    "/lib/x86_64-linux-gnu/libclang-16.so",
)


def has_acsl(source: str) -> bool:
    return "/*@" in source or "//@" in source


def find_matching_brace(source: str, brace_start: int) -> int:
    depth = 0
    i = brace_start
    in_line_comment = False
    in_block_comment = False
    in_string = False
    in_char = False
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
        elif in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 1
        elif in_string:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_string = False
        elif in_char:
            if ch == "\\":
                i += 1
            elif ch == "'":
                in_char = False
        else:
            if ch == "/" and nxt == "/":
                in_line_comment = True
                i += 1
            elif ch == "/" and nxt == "*":
                in_block_comment = True
                i += 1
            elif ch == '"':
                in_string = True
            elif ch == "'":
                in_char = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    raise ValueError("Unmatched function brace")


def _configure_libclang(lib: ctypes.CDLL) -> None:
    lib.clang_createIndex.argtypes = [ctypes.c_int, ctypes.c_int]
    lib.clang_createIndex.restype = ctypes.POINTER(CXIndex)
    lib.clang_disposeIndex.argtypes = [ctypes.POINTER(CXIndex)]
    lib.clang_disposeIndex.restype = None

    lib.clang_parseTranslationUnit.argtypes = [
        ctypes.POINTER(CXIndex),
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_char_p),
        ctypes.c_int,
        ctypes.POINTER(CXUnsavedFile),
        ctypes.c_uint,
        ctypes.c_uint,
    ]
    lib.clang_parseTranslationUnit.restype = ctypes.POINTER(CXTranslationUnit)
    lib.clang_disposeTranslationUnit.argtypes = [ctypes.POINTER(CXTranslationUnit)]
    lib.clang_disposeTranslationUnit.restype = None

    lib.clang_getTranslationUnitCursor.argtypes = [ctypes.POINTER(CXTranslationUnit)]
    lib.clang_getTranslationUnitCursor.restype = CXCursor
    lib.clang_visitChildren.argtypes = [CXCursor, CXCursorVisitor, ctypes.c_void_p]
    lib.clang_visitChildren.restype = ctypes.c_uint

    lib.clang_getCursorKindSpelling.argtypes = [ctypes.c_uint]
    lib.clang_getCursorKindSpelling.restype = CXString
    lib.clang_getCursorSpelling.argtypes = [CXCursor]
    lib.clang_getCursorSpelling.restype = CXString
    lib.clang_getCursorReferenced.argtypes = [CXCursor]
    lib.clang_getCursorReferenced.restype = CXCursor
    lib.clang_getCursorType.argtypes = [CXCursor]
    lib.clang_getCursorType.restype = CXType
    lib.clang_getResultType.argtypes = [CXType]
    lib.clang_getResultType.restype = CXType
    lib.clang_getTypeSpelling.argtypes = [CXType]
    lib.clang_getTypeSpelling.restype = CXString

    lib.clang_getCursorExtent.argtypes = [CXCursor]
    lib.clang_getCursorExtent.restype = CXSourceRange
    lib.clang_getRangeStart.argtypes = [CXSourceRange]
    lib.clang_getRangeStart.restype = CXSourceLocation
    lib.clang_getExpansionLocation.argtypes = [
        CXSourceLocation,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
    ]
    lib.clang_getExpansionLocation.restype = None

    lib.clang_Location_isFromMainFile.argtypes = [CXSourceLocation]
    lib.clang_Location_isFromMainFile.restype = ctypes.c_int

    lib.clang_getCString.argtypes = [CXString]
    lib.clang_getCString.restype = ctypes.c_char_p
    lib.clang_disposeString.argtypes = [CXString]
    lib.clang_disposeString.restype = None


def _load_libclang() -> ctypes.CDLL:
    global _LIBCLANG, _LIBCLANG_LOAD_ATTEMPTED
    if _LIBCLANG_LOAD_ATTEMPTED:
        if _LIBCLANG is not None:
            return _LIBCLANG
        raise RuntimeError(_LIBCLANG_ERROR)
    _LIBCLANG_LOAD_ATTEMPTED = True
    override = os.environ.get("LIBCLANG_FILE")
    candidates = (override,) if override else _LIBCLANG_CANDIDATES
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            lib = ctypes.CDLL(candidate)
            _configure_libclang(lib)
        except (OSError, AttributeError):
            continue
        _LIBCLANG = lib
        return lib
    raise RuntimeError(_LIBCLANG_ERROR)


def _cxstring_to_str(lib: ctypes.CDLL, value: CXString) -> str:
    raw = lib.clang_getCString(value)
    try:
        return raw.decode("utf-8") if raw else ""
    finally:
        lib.clang_disposeString(value)


def _cursor_kind_name(lib: ctypes.CDLL, cursor: CXCursor) -> str:
    return _cxstring_to_str(lib, lib.clang_getCursorKindSpelling(cursor.kind))


def _cursor_spelling(lib: ctypes.CDLL, cursor: CXCursor) -> str:
    return _cxstring_to_str(lib, lib.clang_getCursorSpelling(cursor))


def _type_spelling(lib: ctypes.CDLL, cx_type: CXType) -> str:
    return _cxstring_to_str(lib, lib.clang_getTypeSpelling(cx_type))


def _cursor_start_offset(lib: ctypes.CDLL, cursor: CXCursor) -> int:
    source_range = lib.clang_getCursorExtent(cursor)
    location = lib.clang_getRangeStart(source_range)
    file_ptr = ctypes.c_void_p()
    line = ctypes.c_uint()
    column = ctypes.c_uint()
    offset = ctypes.c_uint()
    lib.clang_getExpansionLocation(location, ctypes.byref(file_ptr), ctypes.byref(line), ctypes.byref(column), ctypes.byref(offset))
    return int(offset.value)


def _visit_children(lib: ctypes.CDLL, cursor: CXCursor) -> list[CXCursor]:
    children: list[CXCursor] = []

    @CXCursorVisitor
    def visitor(child: CXCursor, parent: CXCursor, client_data: ctypes.c_void_p) -> int:
        del parent, client_data
        children.append(child)
        return 1

    lib.clang_visitChildren(cursor, visitor, None)
    return children

def extract_functions(source: str) -> list[FunctionDef]:
    lib = _load_libclang()
    index = lib.clang_createIndex(0, 0)
    translation_unit = None
    try:
        filename = b"input.c"
        contents = source.encode("utf-8")
        unsaved = CXUnsavedFile(Filename=filename, Contents=contents, Length=len(contents))
        args = [
            b"-xc",
            b"-std=gnu11",
            b"-fparse-all-comments",
            b"-Wno-implicit-function-declaration",
            b"-ferror-limit=0",
        ]
        args_array = (ctypes.c_char_p * len(args))(*args)
        translation_unit = lib.clang_parseTranslationUnit(
            index,
            filename,
            args_array,
            len(args),
            ctypes.byref(unsaved),
            1,
            0,
        )
        if not translation_unit:
            raise RuntimeError("libclang could not parse the C source into a translation unit")

        functions: list[FunctionDef] = []
        root = lib.clang_getTranslationUnitCursor(translation_unit)
        declarations = [cursor for cursor in _visit_children(lib, root)
                        if _cursor_kind_name(lib, cursor) == "FunctionDecl"
                        and lib.clang_Location_isFromMainFile(
                            lib.clang_getRangeStart(lib.clang_getCursorExtent(cursor)))]

        def text_offset(cursor: CXCursor) -> int:
            # Clang reports UTF-8 byte offsets; Python slices use character offsets.
            return len(contents[:_cursor_start_offset(lib, cursor)].decode("utf-8"))

        documented_names = {
            _cursor_spelling(lib, cursor) for cursor in declarations
            if has_preceding_acsl(source, text_offset(cursor))
        }
        for cursor in declarations:
            compound_stmt = next(
                (child for child in _visit_children(lib, cursor) if _cursor_kind_name(lib, child) == "CompoundStmt"),
                None,
            )
            if compound_stmt is None:
                continue
            start = text_offset(cursor)
            brace_start = text_offset(compound_stmt)
            end = find_matching_brace(source, brace_start)
            functions.append(
                FunctionDef(
                    name=_cursor_spelling(lib, cursor),
                    return_type=_type_spelling(lib, lib.clang_getResultType(lib.clang_getCursorType(cursor))).strip(),
                    params=source[source.find("(", start) + 1 : source.rfind(")", start, brace_start)].strip(),
                    signature=source[start:brace_start].strip(),
                    start=start,
                    brace_start=brace_start,
                    end=end,
                    body=source[brace_start:end],
                    has_existing_acsl=_cursor_spelling(lib, cursor) in documented_names,
                )
            )
        return functions
    finally:
        if translation_unit is not None:
            lib.clang_disposeTranslationUnit(translation_unit)
        lib.clang_disposeIndex(index)


def has_preceding_acsl(source: str, function_start: int) -> bool:
    annotation = extract_preceding_acsl(source, function_start)
    if annotation is None:
        return False
    annotation = re.sub(r"(?m)^[ \t]*//@", "", annotation)
    annotation = re.sub(r"//[^\n]*", "", annotation)
    return bool(re.search(
        r"\b(?:requires|ensures|assigns|allocates|frees|terminates|decreases|behavior|complete|disjoint)\b",
        annotation,
    ))


def extract_preceding_acsl(source: str, function_start: int) -> str | None:
    prefix = source[:function_start]
    match = re.search(r"(/\*@(?:(?!\*/)[\s\S])*\*/)\s*$", prefix)
    if match is not None:
        return match.group(1)
    match = re.search(r"((?:^[ \t]*//@[^\n]*(?:\n|\Z))+)\s*\Z", prefix, re.MULTILINE)
    return match.group(1) if match is not None else None
