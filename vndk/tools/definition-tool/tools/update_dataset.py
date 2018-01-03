#!/usr/bin/env python3

# This tool updates extracts the information from Android.bp and updates the
# datasets for eligible VNDK libraries.

import argparse
import collections
import csv
import json
import os.path
import posixpath
import re
import sys

def load_make_vars(path):
    result = collections.OrderedDict([
        ('SOONG_LLNDK_LIBRARIES', set()),
        ('SOONG_VNDK_SAMEPROCESS_LIBRARIES', set()),
        ('SOONG_VNDK_CORE_LIBRARIES', set()),
    ])

    assign_len = len(' := ')

    with open(path, 'r') as fp:
        for line in fp:
            for key, value in result.items():
                if line.startswith(key):
                    mod_names = line[len(key) + assign_len:].strip().split(' ')
                    value.update(mod_names)

    return result.values()

def load_install_paths(module_info_path):
    with open(module_info_path, 'r') as fp:
        data = json.load(fp)

    result = set()
    patt = re.compile(
            '.*[\\\\/]target[\\\\/]product[\\\\/][^\\\\/]+([\\\\/].*)$')
    for name, module in data.items():
        for path in module['installed']:
            match = patt.match(path)
            if not match:
                continue
            path = match.group(1)
            path = path.replace(os.path.sep, '/')
            path = path.replace('/lib/', '/${LIB}/')
            path = path.replace('/lib64/', '/${LIB}/')
            result.add(path)
    return result

def main():
    parser =argparse.ArgumentParser()
    parser.add_argument('tag_file')
    parser.add_argument('-o', '--output', required=True)
    parser.add_argument('--make-vars', required=True,
                        help='out/soong/make_vars-$(TARGET).mk')
    parser.add_argument('--module-info', required=True,
                        help='out/target/product/$(TARGET)/module-info.json')
    parser.add_argument('--delete-removed-entries', action='store_true',
                        help='Delete removed shared libs')
    args = parser.parse_args()

    # Load libraries from `out/soong/make_vars-$(TARGET).mk`.
    llndk, vndk_sp, vndk = load_make_vars(args.make_vars)

    # Load eligible list csv file.
    with open(args.tag_file, 'r') as fp:
        reader = csv.reader(fp)
        header = next(reader)
        data = dict()
        regex_patterns = []
        for path, tag, comments in reader:
            if path.startswith('[regex]'):
                regex_patterns.append([path, tag, comments])
            else:
                data[path] = [path, tag, comments]

    # Delete non-existing libraries.
    installed_paths = load_install_paths(args.module_info)

    if args.delete_removed_entries:
        data = { path: row for path, row in data.items()
                           if path in installed_paths }
    else:
        data = { path: row for path, row in data.items() }

    # Reset all /system/${LIB} libraries to FWK-ONLY.
    for path, row in data.items():
        if posixpath.dirname(path) == '/system/${LIB}':
            row[1] = 'FWK-ONLY'

    # Update tags.
    def update_tag(path, tag):
        try:
            data[path][1] = tag
        except KeyError:
            data[path] = [path, tag, '']

    for name in llndk:
        update_tag('/system/${LIB}/' + name + '.so', 'LL-NDK')

    for name in vndk_sp:
        update_tag('/system/${LIB}/' + name + '.so', 'VNDK-SP')
        update_tag('/system/${LIB}/vndk-sp/' + name + '.so', 'VNDK-SP')

    for name in vndk:
        update_tag('/system/${LIB}/' + name + '.so', 'VNDK')
        update_tag('/system/${LIB}/vndk/' + name + '.so', 'VNDK')

    # Workaround for SP-NDK
    libs = [
        'libEGL',
        'libGLESv1_CM',
        'libGLESv2',
        'libGLESv3',
        'libnativewindow',
        'libsync',
        'libvulkan',
    ]
    for name in libs:
        update_tag('/system/${LIB}/' + name + '.so', 'SP-NDK')

    # Workaround for FWK-ONLY-RS
    libs = [
        'libft2',
        'libmediandk',
    ]
    for name in libs:
        update_tag('/system/${LIB}/' + name + '.so', 'FWK-ONLY-RS')

    # Workaround for VNDK-SP-Indirect
    libs = [
        'libbacktrace',
        'liblzma',
        'libunwind',
        'libunwindstack',
    ]
    for name in libs:
        update_tag('/system/${LIB}/' + name + '.so', 'VNDK-SP-Indirect')
        update_tag('/system/${LIB}/vndk-sp/' + name + '.so', 'VNDK-SP-Indirect')

    # Workaround for VNDK-SP-Indirect-Private
    libs = [
        'libblas',
        'libcompiler_rt',
    ]
    for name in libs:
        update_tag('/system/${LIB}/' + name + '.so', 'VNDK-SP-Indirect-Private')
        update_tag('/system/${LIB}/vndk-sp/' + name + '.so',
                   'VNDK-SP-Indirect-Private')

    # Workaround for LL-NDK-Indirect
    libs = [
        'ld-android',
        'libc_malloc_debug',
        'libnetd_client',
    ]
    for name in libs:
        update_tag('/system/${LIB}/' + name + '.so', 'LL-NDK-Indirect')

    for regex in regex_patterns:
        data[regex[0]] = regex

    # Write updated eligible list file.
    with open(args.output, 'w') as fp:
        writer = csv.writer(fp, lineterminator='\n')
        writer.writerow(header)
        writer.writerows(sorted(data.values()))

if __name__ == '__main__':
    sys.exit(main())
