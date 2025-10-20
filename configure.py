"""
Configures the project for building. Invokes splat to split the binary and
creates build files for ninja.
"""
#! /usr/bin/env python3
import argparse
import os
import shutil
import sys
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Union

import ninja_syntax
import splat
import splat.scripts.split as split
from splat.segtypes.linker_entry import LinkerEntry

import yaml

#MARK: Constants
ROOT = Path(__file__).parent.resolve()
TOOLS_DIR = ROOT / "tools"
OUTDIR = "out"

YAML_FILE = Path("config/b3.yaml")
BASENAME = "SLUS_210.50"
LD_PATH = f"{BASENAME}.ld"
ELF_PATH = f"{OUTDIR}/{BASENAME}"
MAP_PATH = f"{OUTDIR}/{BASENAME}.map"
PRE_ELF_PATH = f"{OUTDIR}/{BASENAME}.elf"

COMMON_INCLUDES = "-Iinclude -isystem include/sdk/ee -isystem include/gcc"

CC_DIR = f"{TOOLS_DIR}/cc/bin"
COMMON_COMPILE_FLAGS = f"-x c++ -B{TOOLS_DIR}/cc/lib/gcc-lib/ee/2.95.2/ -O2 -G0 -ffast-math"

WINE = "wine"

GAME_GCC_CMD = f"{CC_DIR}/ee-gcc.exe -c {COMMON_INCLUDES} {COMMON_COMPILE_FLAGS} $in"
COMPILE_CMD = f"{GAME_GCC_CMD}"
if sys.platform == "linux" or sys.platform == "linux2":
    COMPILE_CMD = f"{WINE} {GAME_GCC_CMD}"

CATEGORY_MAP = {
    "P2": "Engine",
    "splice": "Splice",
    "ps2t": "Tooling",
    "sce": "Libs",
    "data": "Data",
}

def clean():
    """
    Clean all products of the build process.
    """
    files_to_clean = [
        ".splache",
        ".ninja_log",
        "build.ninja",
        "permuter_settings.toml",
        "objdiff.json",
        LD_PATH
    ]
    for filename in files_to_clean:
        if os.path.exists(filename):
            os.remove(filename)

    shutil.rmtree("asm", ignore_errors=True)
    shutil.rmtree("assets", ignore_errors=True)
    shutil.rmtree("obj", ignore_errors=True)
    shutil.rmtree("out", ignore_errors=True)


def write_permuter_settings():
    """
    Write the permuter settings file, comprising the compiler and assembler commands.
    """
    with open("permuter_settings.toml", "w", encoding="utf-8") as f:
        f.write(f"""compiler_command = "{COMPILE_CMD} -D__GNUC__"
assembler_command = "mips-linux-gnu-as -march=r5900 -mabi=eabi -Iinclude"
compiler_type = "gcc"

[preserve_macros]

[decompme.compilers]
"tools/build/cc/gcc/gcc" = "ee-gcc2.96"
""")

#MARK: Build
def build_stuff(linker_entries: List[LinkerEntry], skip_checksum=False, objects_only=False, dual_objects=False):
    """
    Build the objects and the final ELF file.
    If objects_only is True, only build objects and skip linking/checksum.
    If dual_objects is True, build objects twice: once normally, once with -DSKIP_ASM.
    """
    built_objects: Set[Path] = set()
    objdiff_units = []  # For objdiff.json

    def build(
        object_paths: Union[Path, List[Path]],
        src_paths: List[Path],
        task: str,
        variables: Dict[str, str] = None,
        implicit_outputs: List[str] = None,
        out_dir: str = None,
        extra_flags: str = "",
        collect_objdiff: bool = False,
        orig_entry=None,
    ):
        """
        Helper function to build objects.
        """
        # Handle none parameters
        if variables is None:
            variables = {}

        if implicit_outputs is None:
            implicit_outputs = []

        # Convert object_paths to list if it is not already
        if not isinstance(object_paths, list):
            object_paths = [object_paths]

        # Only rewrite output path to .o if out_dir is set (i.e. --objects mode)
        if out_dir:
            new_object_paths = []
            for obj in object_paths:
                obj = Path(obj)
                stem = obj.stem
                if obj.suffix in [".s", ".c"]:
                    stem = obj.stem
                else:
                    if obj.suffix == ".o" and obj.with_suffix("").suffix in [".s", ".c"]:
                        stem = obj.with_suffix("").stem
                target_dir = out_dir if out_dir else obj.parent
                new_obj = Path(target_dir) / (stem + ".o")
                new_object_paths.append(new_obj)
            object_paths = new_object_paths

        # Otherwise, use the original object_paths (with .s.o, .c.o, etc.)

        # Add object paths to built_objects
        for idx, object_path in enumerate(object_paths):
            if object_path.suffix == ".o":
                built_objects.add(object_path)

            # Add extra_flags to variables if present
            build_vars = variables.copy()
            if extra_flags:
                build_vars["cflags"] = extra_flags
            ninja.build(
                outputs=[str(object_path)],
                rule=task,
                inputs=[str(s) for s in src_paths],
                variables=build_vars,
                implicit_outputs=implicit_outputs,
            )

            # Collect for objdiff.json if requested
            if collect_objdiff and orig_entry is not None:
                src = src_paths[0] if src_paths else None
                if src:
                    src = Path(src)
                    # Always use the final "matched" name, i.e. as if it will be in src/ with no asm/ prefix
                    try:
                        # If the file is in asm/, replace asm/ with nothing (just drop asm/)
                        if src.parts[0] == "asm":
                            rel = Path(*src.parts[1:])
                        elif src.parts[0] == "src":
                            rel = Path(*src.parts[1:])
                        else:
                            rel = src
                        # Remove extension for the name
                        name = str(rel.with_suffix(""))
                    except Exception:
                        name = str(src.with_suffix(""))
                else:
                    name = object_path.stem
                    # Ensure `rel` is defined so later code can compute src-based paths
                    try:
                        rel = Path(object_path)
                    except Exception:
                        rel = Path(str(object_path))

                if "target" in str(object_path):
                    target_path = str(object_path)

                    # Determine if a .c or .cpp file exists in src/ for this unit (recursively)
                    src_base = rel.with_suffix("")
                    src_c_files = list(Path("src").rglob(src_base.name + ".c"))
                    src_cpp_files = list(Path("src").rglob(src_base.name + ".cpp"))
                    has_src = bool(src_c_files or src_cpp_files)

                    # Determine the category based on the name
                    categories = [name.split("/")[0]]
                    if "P2/splice/" in name:
                        categories.append("splice")
                    elif "P2/ps2t" in name:
                        categories.append("ps2t")

                    unit = {
                        "name": name,
                        "target_path": target_path,
                        "metadata": {
                            "progress_categories": categories,
                        }
                    }

                    if has_src:
                        # Replace only the path segment named 'target' with 'current',
                        # preserving any filenames that may contain the substring "target".
                        op = Path(object_path)
                        parts = list(op.parts)
                        for idx, part in enumerate(parts):
                            if part == "target":
                                parts[idx] = "current"
                                break
                        base_path = str(Path(*parts))
                        unit["base_path"] = base_path
                    objdiff_units.append(unit)

    ninja = ninja_syntax.Writer(open(str(ROOT / "build.ninja"), "w", encoding="utf-8"), width=9999)

    #MARK: Rules
    cross = "mips-linux-gnu-"

    ld_args = "-EL -T config/undefined_syms_auto.txt -T config/undefined_funcs_auto.txt -Map $mapfile -T $in -o $out"

    ninja.rule(
        "as",
        description="as $in",
        command=f"cpp {COMMON_INCLUDES} $in -o  - | {cross}as -no-pad-sections -EL -march=5900 -mabi=eabi -Iinclude -o $out",
    )

    ninja.rule(
        "cc",
        description="cc $in",
        command=f"{COMPILE_CMD} $cflags -o $out && {cross}strip $out -N dummy-symbol-name",
    )

    ninja.rule(
        "ld",
        description="link $out",
        command=f"{cross}ld {ld_args}",
    )

    ninja.rule(
        "sha1sum",
        description="sha1sum $in",
        command="sha1sum -c $in && touch $out",
    )

    ninja.rule(
        "elf",
        description="elf $out",
        command=f"{cross}objcopy $in $out -O binary",
    )

    #MARK: Build
    # Build all the objects
    for entry in linker_entries:
        seg = entry.segment

        if seg.type[0] == ".":
            continue

        if entry.object_path is None:
            continue

        if isinstance(seg, splat.segtypes.common.asm.CommonSegAsm) or isinstance(
            seg, splat.segtypes.common.data.CommonSegData
        ):
            if dual_objects:
                build(entry.object_path, entry.src_paths, "as", out_dir="obj/target", collect_objdiff=True, orig_entry=entry)
                build(entry.object_path, entry.src_paths, "as", out_dir="obj/current", extra_flags="-DSKIP_ASM")
            else:
                build(entry.object_path, entry.src_paths, "as")
        elif isinstance(seg, splat.segtypes.common.c.CommonSegC):
            if dual_objects:
                print(f"Building C segment: {entry.object_path} from {entry.src_paths}")
                build(entry.object_path, entry.src_paths, "cc", out_dir="obj/target", collect_objdiff=True, orig_entry=entry)
                build(entry.object_path, entry.src_paths, "cc", out_dir="obj/current", extra_flags="-DSKIP_ASM")
            else:
                build(entry.object_path, entry.src_paths, "cc")
        elif isinstance(seg, splat.segtypes.common.databin.CommonSegDatabin):
            if dual_objects:
                build(entry.object_path, entry.src_paths, "as", out_dir="obj/target", collect_objdiff=True, orig_entry=entry)
                build(entry.object_path, entry.src_paths, "as", out_dir="obj/current", extra_flags="-DSKIP_ASM")
            else:
                build(entry.object_path, entry.src_paths, "as")
        elif isinstance(seg, splat.segtypes.common.rodatabin.CommonSegRodatabin):
            if dual_objects:
                build(entry.object_path, entry.src_paths, "as", out_dir="obj/target", collect_objdiff=True, orig_entry=entry)
                build(entry.object_path, entry.src_paths, "as", out_dir="obj/current", extra_flags="-DSKIP_ASM")
            else:
                build(entry.object_path, entry.src_paths, "as")
        elif isinstance(seg, splat.segtypes.common.textbin.CommonSegTextbin):
            if dual_objects:
                build(entry.object_path, entry.src_paths, "as", out_dir="obj/target", collect_objdiff=True, orig_entry=entry)
                build(entry.object_path, entry.src_paths, "as", out_dir="obj/current", extra_flags="-DSKIP_ASM")
            else:
                build(entry.object_path, entry.src_paths, "as")
        elif isinstance(seg, splat.segtypes.common.bin.CommonSegBin):
            if dual_objects:
                build(entry.object_path, entry.src_paths, "as", out_dir="obj/target", collect_objdiff=True, orig_entry=entry)
                build(entry.object_path, entry.src_paths, "as", out_dir="obj/current", extra_flags="-DSKIP_ASM")
            else:
                build(entry.object_path, entry.src_paths, "as")
        else:
            print(f"ERROR: Unsupported build segment type {seg.type}")
            sys.exit(1)

    if objects_only:
        # Write objdiff.json if dual_objects (i.e. --objects)
        if dual_objects:
            objdiff = {
                "$schema": "https://raw.githubusercontent.com/encounter/objdiff/main/config.schema.json",
                "custom_make": "ninja",
                "custom_args": [],
                "build_target": False,
                "build_base": True,
                "watch_patterns": [
                    "src/**/*.c",
                    "src/**/*.cp",
                    "src/**/*.cpp",
                    "src/**/*.cxx",
                    "src/**/*.h",
                    "src/**/*.hp",
                    "src/**/*.hpp",
                    "src/**/*.hxx",
                    "src/**/*.s",
                    "src/**/*.S",
                    "src/**/*.asm",
                    "src/**/*.inc",
                    "src/**/*.py",
                    "src/**/*.yml",
                    "src/**/*.txt",
                    "src/**/*.json"
                ],
                "units": objdiff_units,
                "progress_categories": [ {"id": id, "name": name} for id, name in CATEGORY_MAP.items() ],
            }
            with open("objdiff.json", "w", encoding="utf-8") as f:
                json.dump(objdiff, f, indent=2)
        return

    ninja.build(
        PRE_ELF_PATH,
        "ld",
        LD_PATH,
        implicit=[str(obj) for obj in built_objects],
        variables={"mapfile": MAP_PATH},
    )

    ninja.build(
        ELF_PATH,
        "elf",
        PRE_ELF_PATH,
    )

    if not skip_checksum:
        ninja.build(
            ELF_PATH + ".ok",
            "sha1sum",
            "config/checksum.sha1",
            implicit=[ELF_PATH],
        )
    else:
        print("Skipping checksum step")

#MARK: Short loop fix
# Pattern to workaround unintended nops around loops
COMMENT_PART = r"\/\* (.+) ([0-9A-Z]{2})([0-9A-Z]{2})([0-9A-Z]{2})([0-9A-Z]{2}) \*\/"
INSTRUCTION_PART = r"(\b(bne|bnel|beq|beql|bnez|bnezl|beqzl|bgez|bgezl|bgtz|bgtzl|blez|blezl|bltz|bltzl|b)\b.*)"
OPCODE_PATTERN = re.compile(f"{COMMENT_PART}  {INSTRUCTION_PART}")

PROBLEMATIC_FUNCS = set(
    [
        "UpdateJtActive__FP2JTP3JOYf", # P2/jt
        "AddMatrix4Matrix4__FP7MATRIX4N20", # P2/mat
        "FInvertMatrix__FiPfT1", # P2/mat
        "PwarpFromOid__F3OIDT0", # P2/xform
        "RenderMsGlobset__FP2MSP2CMP2RO", # P2/ms
        "ProjectBlipgTransform__FP5BLIPGfi", # P2/blip
        "DrawTvBands__FP2TVR4GIFS", # P2/tv
        "LoadShadersFromBrx__FP18CBinaryInputStream", # P2/shd
        "FillShaders__Fi", # P2/shd
        "FUN_001aea70", # P2/screen
        "ApplyDzg__FP3DZGiPiPPP2SOff", # P2/dzg
        "BounceRipgRips__FP4RIPG", # P2/rip
        "UpdateStepPhys__FP4STEP", # P2/step
        "PredictAsegEffect__FP4ASEGffP3ALOT3iP6VECTORP7MATRIX3T6T6", # P2/aseg
        "ExplodeExplsExplso__FP5EXPLSP6EXPLSO", # P2/emitter
        "UpdateShadow__FP6SHADOWf" # P2/shadow
    ]
)

def replace_instructions_with_opcodes(asm_folder: Path) -> None:
    """
    Replace branch instructions with raw opcodes for functions that trigger the short loop bug.
    """
    nm_folder = ROOT / asm_folder / "nonmatchings"

    for p in nm_folder.rglob("*.s"):
        if p.stem not in PROBLEMATIC_FUNCS:
            continue

        with p.open("r") as file:
            content = file.read()

        if re.search(OPCODE_PATTERN, content):
            # Reference found
            # Embed the opcode, we have to swap byte order for correct endianness
            content = re.sub(
                OPCODE_PATTERN,
                r"/* \1 \2\3\4\5 */  .word      0x\5\4\3\2 /* \6 */",
                content,
            )

            # Write the updated content back to the file
            with p.open("w") as file:
                file.write(content)

def promote_local_labels(yaml_path: Path, splat_config: dict):
    """
    Scans generated assembly files for cross-file local label references
    and promotes them to global labels to fix linker errors.
    """
    print("Checking for local labels to promote...")
    asm_path = Path(splat_config["options"]["asm_path"])
    
    with open(yaml_path, "r") as f:
        yaml_data = yaml.safe_load(f)

    # Find all segment groups by navigating the nested structure
    groups = {}
    for segment in yaml_data["segments"]:
        # Check if this is a dictionary-style segment with a 'subsegments' list
        if isinstance(segment, dict) and "subsegments" in segment:
            # Now iterate through the list of subsegments
            for subsegment in segment["subsegments"]:
                # A subsegment is a list like [start, type, name, {options}]
                # The options dict with our 'group' tag is at index 3
                if len(subsegment) > 3 and isinstance(subsegment[3], dict) and "group" in subsegment[3]:
                    group_name = subsegment[3]["group"]
                    segment_name = subsegment[2]
                    # We only care about 'asm' segments
                    if subsegment[1] == "asm":
                        if group_name not in groups:
                            groups[group_name] = []
                        groups[group_name].append(segment_name)
    
    if not groups:
        print("No label groups found.")
        return

    # The rest of this function (the 3 passes) remains the same as it was correct.
    for group_name, segment_names in groups.items():
        print(f"Processing group '{group_name}'...")
        
        files_in_group = []
        for seg_name in segment_names:
            # Strategy: Check for a directory first, then fall back to a single file.

            # 1. Check for a directory (e.g., 'asm/nonmatchings/text' or 'asm/text')
            dir_path_nonmatching = asm_path / "nonmatchings" / seg_name
            dir_path_main = asm_path / seg_name
            
            # 2. Check for a single file (e.g., 'asm/text.s')
            file_path = asm_path / f"{seg_name}.s"

            if dir_path_nonmatching.is_dir():
                print(f"  Found asm directory: {dir_path_nonmatching}")
                files_in_group.extend(list(dir_path_nonmatching.rglob("*.s")))
            elif dir_path_main.is_dir():
                print(f"  Found asm directory: {dir_path_main}")
                files_in_group.extend(list(dir_path_main.rglob("*.s")))
            elif file_path.is_file():
                print(f"  Found asm file: {file_path}")
                files_in_group.append(file_path)
            else:
                print(f"  Warning: Could not find asm directory or file for segment '{seg_name}'")

        print(f"  Total assembly files found: {len(files_in_group)}")
        if not len(files_in_group):
            print(f"No assembly files found for group '{group_name}'. Skipping.")
            continue

        # Pass 1: Find all local label definitions and where they live
        label_definitions = {}
        label_def_regex = re.compile(r"^\s*(\.L[0-9A-F]{8}):")
        for file_path in files_in_group:
            with open(file_path, "r") as f:
                for line in f:
                    match = label_def_regex.match(line)
                    if match:
                        #print(f"    Found label definition: {match.group(1)} in {file_path}")
                        label_definitions[match.group(1)] = file_path

        # Pass 2: Find all labels that are referenced from a different file
        labels_to_promote = set()
        label_ref_regex = re.compile(r"(\.L[0-9A-F]{8})\b")
        for file_path in files_in_group:
            with open(file_path, "r") as f:
                content = f.read()
                for match in label_ref_regex.finditer(content):
                    #print(f"    Found label reference: {match.group(1)} in {file_path}")
                    label = match.group(1)
                    if label in label_definitions and label_definitions[label] != file_path:
                        labels_to_promote.add(label)

        if not len(labels_to_promote):
            print(f"No cross-file local labels found in group '{group_name}'.")
            continue
        
        print(f"Promoting {len(labels_to_promote)} labels: {', '.join(sorted(list(labels_to_promote)))}...")

        # Pass 3: Rewrite the files, promoting the necessary labels
        for file_path in files_in_group:
            with open(file_path, "r") as f:
                content = f.read()
            
            original_content = content
            
            for label in labels_to_promote:
                global_label = label[1:] # Remove the leading dot
                # print(f"  Promoting label {label} to {global_label} in {file_path}")
                content = re.sub(f"^\s*{re.escape(label)}:", f"glabel {global_label}", content, flags=re.MULTILINE)
                content = re.sub(f"{re.escape(label)}\\b", global_label, content)
            
            if content != original_content:
                with open(file_path, "w") as f:
                    f.write(content)

#MARK: Main
def main():
    """
    Main function, parses arguments and runs the configuration.
    """
    parser = argparse.ArgumentParser(description="Configure the project")
    parser.add_argument(
        "-c",
        "--clean",
        help="Clean artifacts and build",
        action="store_true",
    )
    parser.add_argument(
        "-C",
        "--clean-only",
        help="Only clean artifacts",
        action="store_true",
    )
    parser.add_argument(
        "-s",
        "--skip-checksum",
        help="Skip the checksum step",
        action="store_true",
    )
    parser.add_argument(
        "--objects",
        help="Build objects to obj/target and obj/current (with -DSKIP_ASM), skip linking and checksum",
        action="store_true",
    )
    parser.add_argument(
        "-noloop",
        "--no-short-loop-workaround",
        help="Do not replace branch instructions with raw opcodes for functions that trigger the short loop bug",
        action="store_true",
    )
    args = parser.parse_args()

    do_clean = (args.clean or args.clean_only) or False
    do_skip_checksum = args.skip_checksum or False
    do_objects = args.objects or False

    if do_clean:
        clean()
        if args.clean_only:
            return

    split.main([YAML_FILE], modes="all", verbose=False)

    promote_local_labels(YAML_FILE, split.config)

    linker_entries = split.linker_writer.entries

    if do_objects:
        build_stuff(linker_entries, skip_checksum=True, objects_only=True, dual_objects=True)
    else:
        build_stuff(linker_entries, do_skip_checksum)

    write_permuter_settings()

    if not args.no_short_loop_workaround:
        replace_instructions_with_opcodes(split.config["options"]["asm_path"])

if __name__ == "__main__":
    main()
