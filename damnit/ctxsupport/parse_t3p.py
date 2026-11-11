#!/usr/bin/env python3
"""
parse_t3p.py

Parses Timepix3 / Pixet .t3p.info metadata files and extracts key acquisition metadata,
specifically the "Start time" ("Acquisition start time") field (double[1]).

Usage examples:
    # 1. Matching by pattern ending:
    timestamp = get_start_time("*0000.t3p.info")
    timestamp = get_start_time("/path/to/scan/*0000.t3p.info")

    # 2. Passing directory directly:
    timestamp = get_start_time("/path/to/scan")

    # 3. Passing exact file path:
    timestamp = get_start_time("tmp/Setup_04141_raw_data_00000.t3p.info")
"""

import sys
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Union


def resolve_single_info_file(
    path_or_pattern: Union[str, Path] = "*00000.t3p.info",
    search_dir: Optional[Union[str, Path]] = None,
    default_suffix: str = "00000.t3p.info",
) -> Path:
    """
    Finds exactly one file matching the specified path, pattern, or suffix.
    Uses `endswith` matching for the filename suffix.

    Raises:
        FileNotFoundError: If 0 matching files are found.
        ValueError: If more than 1 matching file is found.

    Returns:
        Path: The single matching file path.
    """
    p_str = str(path_or_pattern)
    p = Path(p_str)

    # 1. If explicit search_dir is provided, look inside search_dir
    if search_dir is not None:
        parent_dir = Path(search_dir).resolve()
        filename_part = p.name
        suffix = filename_part.split("*", 1)[-1] if "*" in filename_part else filename_part
    # 2. Existing regular file with no wildcard
    elif "*" not in p_str and p.is_file():
        return p.resolve()
    # 3. Path contains wildcard '*'
    elif "*" in p_str:
        parent_dir = p.parent.resolve() if str(p.parent) != "" else Path.cwd().resolve()
        filename_part = p.name
        suffix = filename_part.split("*", 1)[-1] if "*" in filename_part else filename_part
    # 4. Path is an existing directory
    elif p.is_dir():
        parent_dir = p.resolve()
        suffix = default_suffix
    # 5. Relative filename or suffix without wildcard
    else:
        parent_dir = p.parent.resolve() if str(p.parent) != "" else Path.cwd().resolve()
        suffix = p.name

    if not parent_dir.is_dir():
        raise FileNotFoundError(f"Directory does not exist: {parent_dir}")

    # Match files using endswith
    matching: List[Path] = [
        f for f in sorted(parent_dir.iterdir())
        if f.is_file() and f.name.endswith(suffix)
    ]

    if len(matching) == 0:
        raise FileNotFoundError(
            f"No file ending with '{suffix}' found in directory: {parent_dir}"
        )
    elif len(matching) > 1:
        names = [f.name for f in matching]
        raise ValueError(
            f"Expected exactly 1 file ending with '{suffix}' in {parent_dir}, but found {len(matching)}: {names}"
        )

    return matching[0]


def get_start_time(
    path_or_pattern: Union[str, Path] = "*00000.t3p.info",
    search_dir: Optional[Union[str, Path]] = None,
) -> float:
    """
    Finds the single .t3p.info file matching the pattern/path (via endswith)
    and extracts the 'Start time' ('Acquisition start time') double[1] value.

    Args:
        path_or_pattern: A file path, pattern with wildcard (e.g. '*0000.t3p.info',
                         '/path/to/*00000.t3p.info'), or directory path.
        search_dir: Optional directory to search in if not included in path_or_pattern.

    Raises:
        FileNotFoundError: If 0 matching files are found, or 'Start time' field is missing.
        ValueError: If more than 1 matching file is found.

    Returns:
        float: Start timestamp in seconds (e.g. 1794335662.843).
    """
    file_path = resolve_single_info_file(path_or_pattern, search_dir=search_dir)

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        lines = [line.strip() for line in f]

    for i, line in enumerate(lines):
        # Match exact header: "Start time" ("Acquisition start time"):
        if line.startswith('"Start time"') and '("Acquisition start time")' in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                candidate = lines[j]
                if not candidate:
                    continue
                # Skip the type declaration line (e.g. 'double[1]')
                if candidate.startswith("double") or candidate.startswith("["):
                    continue
                try:
                    return float(candidate.split()[0])
                except (ValueError, IndexError):
                    pass

    raise FileNotFoundError(f"'Start time' field not found in file: {file_path}")


def get_start_time_datetime(
    path_or_pattern: Union[str, Path] = "*00000.t3p.info",
    search_dir: Optional[Union[str, Path]] = None,
) -> datetime:
    """
    Extracts the acquisition start time as a Python datetime object.
    """
    ts = get_start_time(path_or_pattern, search_dir=search_dir)
    return datetime.fromtimestamp(ts)


def parse_t3p_info(file_path: Union[str, Path]) -> Dict[str, dict]:
    """
    Parses an entire .t3p.info file into a dictionary of fields with their
    description, datatype, and parsed value.
    """
    resolved_path = resolve_single_info_file(file_path)
    data = {}

    with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    pattern = re.compile(
        r'"([^"]+)"\s*\("([^"]*)"\):\s*\n([^\n]+)\n(.*?)(?=\n"[^"]+"\s*\("[^"]*"\):|\Z)',
        re.DOTALL
    )

    for match in pattern.finditer(content):
        key = match.group(1).strip()
        desc = match.group(2).strip()
        data_type = match.group(3).strip()
        raw_val = match.group(4).strip()

        parsed_val = raw_val
        if data_type.startswith("double"):
            parts = raw_val.split()
            if len(parts) == 1:
                try:
                    parsed_val = float(parts[0])
                except ValueError:
                    pass
            else:
                try:
                    parsed_val = [float(x) for x in parts]
                except ValueError:
                    pass
        elif data_type.startswith(("u32", "i32", "u16", "i16", "u8", "i8")):
            parts = raw_val.split()
            if len(parts) == 1:
                try:
                    parsed_val = int(parts[0])
                except ValueError:
                    pass
            else:
                try:
                    parsed_val = [int(x) for x in parts]
                except ValueError:
                    pass

        data[key] = {
            "description": desc,
            "type": data_type,
            "value": parsed_val,
            "raw": raw_val,
        }

    return data


def find_start_times(
    folder_or_file: Union[str, Path],
    pattern: str = "*0000*.info",
    recursive: bool = True
) -> Dict[Path, float]:
    """
    Searches for files matching `pattern` and extracts the start time from each.
    """
    target = Path(folder_or_file).resolve()
    results = {}

    if target.is_file():
        st = get_start_time(target)
        results[target] = st
        return results

    if target.is_dir():
        file_iterator = target.rglob(pattern) if recursive else target.glob(pattern)
        for f in sorted(file_iterator):
            if f.is_file():
                try:
                    st = get_start_time(f)
                    results[f] = st
                except (FileNotFoundError, ValueError):
                    pass

    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_t3p.py <file_or_pattern>")
        print("Example: python parse_t3p.py 'tmp/*0000.t3p.info'")
        print("Example: python parse_t3p.py 'tmp/*00000.t3p.info'")
        print("Example: python parse_t3p.py tmp/Setup_04141_raw_data_00000.t3p.info")
        sys.exit(1)

    arg = sys.argv[1]
    try:
        matched_file = resolve_single_info_file(arg)
        st = get_start_time(matched_file)
        dt = get_start_time_datetime(matched_file)
        print(f"Matched file:           {matched_file}")
        print(f"Start time (double[1]): {st}")
        print(f"Start time (datetime):   {dt}")
    except (FileNotFoundError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
