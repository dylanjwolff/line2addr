#!/usr/bin/env python3
import argparse
import json
import os

from collections import defaultdict

import colorama

import elftools.elf.elffile as elf

def redhex(num, padding):
    if num == '':
        return ' '*padding
    return colorama.Fore.RED + ("{:"+str(padding)+"x}").format(num)+ colorama.Fore.RESET

def yellownum(num, padding):
    if num == '':
        return ' '*padding
    return colorama.Fore.YELLOW + ("{:" + str(padding) + "d}").format(num) + colorama.Fore.RESET

def green(string):
    return colorama.Fore.LIGHTGREEN_EX + string + colorama.Fore.RESET

def get_lines(binary, base_address=0x0):
    elf_binary = elf.ELFFile(binary)
    dwarf = elf_binary.get_dwarf_info()
    lines = defaultdict(lambda: defaultdict(lambda:[]))
    for cu in dwarf.iter_CUs():
        lp = dwarf.line_program_for_CU(cu)
        files = lp['file_entry']
        directories = ["."] + [str(d, 'utf8') for d in lp['include_directory']]
        for lpe in lp.get_entries():
            if lpe.state:
                lfile = files[lpe.state.file-1]
                (lines[(directories[lfile['dir_index']], str(lfile['name'], 'utf8'))]
                    [lpe.state.line].append((lpe.command, lpe.state.address+base_address)))
    return lines

def display_file_line(filename, lineno, lines):
    # Also needs to be fixed here
    referenced_files = {pair[1]:(pair[0],pair[1]) for pair in lines}
    bf = os.path.basename(filename)
    reffile = referenced_files.get(bf, None)
    print(f"refile {reffile}")

    if reffile:
        for line, addr in lines[reffile][lineno]:
            print(hex(addr))
    else:
        print("{} is not references in the executable".format(filename))

def print_line(**kwargs):
    if kwargs['options']['display_dwarf']:
        print("{} {:3} {} {}".format(
            yellownum(kwargs['lineno'], 3),
            kwargs['opcode'],
            redhex(kwargs['addr'], 8),
            kwargs['line']))
    else:
        print("{} {} {}".format(
            yellownum(kwargs['lineno'], 3),
            redhex(kwargs['addr'], 8),
            kwargs['line']))

def resolve_file(dirname, basename, lookup):
    """
    If a filename is unique, use it. If it is not,
    check the parent directories until disambiguation is achieved.
    """
    if basename not in lookup:
        return None
    reference_list = lookup[basename]
    dirname_path = os.path.split(dirname)
    matches = [(os.path.split(match[0]), match[0], match[1]) for match in reference_list]
    if len(matches) == 1:
        return (matches[0][1], matches[0][2])
    while matches:
        matches = [(os.path.split(match[0][0]), match[1], match[2]) for match in matches
            if os.path.normpath(match[0][-1]) == os.path.normpath(dirname_path[-1])]
        dirname_path = os.path.split(dirname_path[0])
        if len(matches) == 1:
            return (matches[0][1], matches[0][2])
    return None

def construct_reference_lookup(lines):
    lookup = defaultdict(lambda: [])
    for (directory, name) in lines:
        lookup[name].append((directory, name))
    return lookup

def display_file(filename, lines, display_options):
    # This is the main issue
    referenced_files = construct_reference_lookup(lines)
    abspath = os.path.abspath(filename)
    dirname = os.path.dirname(abspath)
    basename = os.path.basename(abspath)

    with open(filename) as srcfile:
        reffile = resolve_file(dirname, basename, referenced_files)
        if reffile:
            for lineno, line in enumerate(srcfile.readlines(), 1):
                if lineno in lines[reffile]:
                    addresses = lines[reffile][lineno]
                    opcode, addr = addresses[0]
                    print_line(lineno=lineno, opcode=opcode, addr=addr, line=line[:-1], options=display_options)
                    for i, (opcode, addr) in enumerate(addresses[1:], 1):
                        print_line(lineno='', opcode=opcode, addr=addr, line='', options=display_options)
                else:
                    print_line(lineno=lineno, opcode='', addr='', line=line[:-1], options=display_options)
        else:
            print("{} is not referenced in the executable".format(filename))

def normalize_hex(hexstring):
    hs = hexstring
    if hexstring.startswith("0"):
        hs = hexstring[2:]
    elif hexstring.startswith("x"):
        hs = hexstring[1:]
    return int(hs, 16)

def get_binary_lines(binary, base_addr="0x0"):
    base_address = normalize_hex(base_addr)

    with open(binary, "rb") as binary:
        lines = get_lines(binary, base_address)
    return lines



def get_file_line(filename, lineno, binary, bin_lines=None, base_addr="0x0"):
    lineno = int(lineno)
    lines = bin_lines

    if lines is None:
        base_address = normalize_hex(base_addr)

        with open(binary, "rb") as binary:
            lines = get_lines(binary, base_address)

    # Also needs to be fixed here
    referenced_files = {pair[1]:(pair[0],pair[1]) for pair in lines}
    bf = os.path.basename(filename)
    reffile = referenced_files.get(bf, None)

    addrs = []
    if reffile:
        for line, addr in lines[reffile][lineno]:
            print(hex(addr))
            addrs.append(hex(addr))
        return addrs
    else:
        print("{} is not references in the executable".format(filename))


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", "-b", required=True,
        help="binary to resolve addresses for")
    parser.add_argument("--json-db", "-j", action="store_true",
        help="dump DWARF database to json output (WIP)")
    parser.add_argument("--file", "-f",
        help="print addresses for target FILE")
    parser.add_argument("--line", "-l", type=int,
        help="print address for target LINE instead (also needs FILE)")
    parser.add_argument("--directory", "-d",
        help="print addresses for all files provided src root DIRECTORY")
    parser.add_argument("--base-address", "-a", default='0x0',
        help="add BASE_ADDRESS to all addresses")
    parser.add_argument("--dwarf", action="store_true",
        help="display additional DWARF information for lines")
    options = parser.parse_args()

    base_address = normalize_hex(options.base_address)

    display_options = {"display_dwarf": options.dwarf }

    with open(options.binary, "rb") as binary:
        lines = get_lines(binary, base_address)
    if options.json_db:
        print(json.dumps(
            {
                "{}/{}".format(key[0], key[1]) : {
                    lineno : [[cmd_addr[0], hex(cmd_addr[1])] for cmd_addr in lines[key][lineno]]
                    for lineno in lines[key]
                }
                for key in lines
            }))
    if options.file and options.line:
        display_file_line(options.file, options.line, lines)
    if options.file and not options.line:
        display_file(options.file, lines, display_options)
    if options.directory:
        for srcfile in lines:
            fullsrcpath = os.path.join(srcfile[0], srcfile[1])
            fullpath = os.path.join(options.directory, fullsrcpath)
            print(green(fullpath + ":"))
            display_file(fullpath, lines, display_options)

if __name__ == "__main__":
    cli()
