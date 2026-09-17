# python_pipes.py

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

_REFERENCE = re.compile(r"^@([A-Za-z_][A-Za-z0-9_]*)(?::([a-z]+))?$")
SUPPORTED_TYPES = ("str", "bytes", "json", "lines", "int", "float")

@dataclass(frozen=True)
class PythonPipeReference:
    """A parsed `@variable:datatype` endpoint."""

    name: str
    datatype: str

def parse_reference(value: str) -> Optional[PythonPipeReference]:
    """Parse an exact typed Python-variable reference.

    Args:
        value: One parsed command word.

    Returns:
        A reference, or ``None`` when the word is not `@` syntax.

    Raises:
        ValueError: If the reference uses an unsupported datatype.
    """
    match = _REFERENCE.fullmatch(value)
    if match is None:
        return None
    datatype = match.group(2) or "str"
    if datatype not in SUPPORTED_TYPES:
        raise ValueError(
            "unsupported Python pipe datatype {0}; expected one of {1}".format(
                datatype, ", ".join(SUPPORTED_TYPES)
            )
        )
    return PythonPipeReference(match.group(1), datatype)

def encode_variable(reference: PythonPipeReference, namespace: Dict[str, Any]) -> bytes:
    """Serialize a Python variable for pipeline input.

    Args:
        reference: Variable name and requested datatype.
        namespace: Persistent native Python namespace.

    Returns:
        Bytes to provide to the first external process.

    Raises:
        ValueError: If the variable is missing or incompatible with its type.
    """
    if reference.name not in namespace:
        raise ValueError("Python variable is not defined: {0}".format(reference.name))
    value = namespace[reference.name]
    try:
        if reference.datatype == "bytes":
            if not isinstance(value, (bytes, bytearray, memoryview)):
                raise TypeError("bytes requires a bytes-like value")
            return bytes(value)
        if reference.datatype == "json":
            return (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
        if reference.datatype == "lines":
            return "".join("{0}\n".format(item) for item in value).encode("utf-8")
        if reference.datatype == "int":
            return str(int(value)).encode("utf-8")
        if reference.datatype == "float":
            return str(float(value)).encode("utf-8")
        return str(value).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError(
            "could not encode @{0}:{1}: {2}".format(
                reference.name, reference.datatype, error
            )
        ) from error

def decode_variable(reference: PythonPipeReference, data: bytes) -> Any:
    """Decode captured pipeline bytes into a Python value.

    Args:
        reference: Destination name and requested datatype.
        data: Exact bytes captured from the pipeline.

    Returns:
        Decoded Python value.

    Raises:
        ValueError: If bytes cannot be decoded as the requested datatype.
    """
    if reference.datatype == "bytes":
        return data
    try:
        text = data.decode("utf-8")
        if reference.datatype == "json":
            return json.loads(text)
        if reference.datatype == "lines":
            return text.splitlines()
        if reference.datatype == "int":
            return int(text.strip())
        if reference.datatype == "float":
            return float(text.strip())
        return text
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("could not decode @{0}:{1}: {2}".format(reference.name, reference.datatype, error)) from error
