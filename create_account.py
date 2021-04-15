#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# pylint: disable=missing-docstring

import os
import subprocess
import shutil

def main():
    cmd = './kms create -k key_file'
    kms_create = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = kms_create.stdout.readlines()[-1].decode().strip()
    print("kms create output:", output)
    # output should looks like: key_id:1,address:0xba21324990a2feb0a0b6ca16b444b5585b841df9
    infos = output.split(',')
    key_id = infos[0].split(':')[1]
    address = infos[1].split(':')[1]

    current_dir = os.path.abspath(os.curdir)
    dir = os.path.join(current_dir, address)
    if not os.path.exists(dir):
        os.makedirs(dir)
    
    shutil.move(os.path.join(current_dir, 'kms.db'), os.path.join(dir, 'kms.db'))
    shutil.move(os.path.join(current_dir, 'key_file'), os.path.join(dir, 'key_file'))

    path = os.path.join(dir, 'key_id')
    with open(path, 'wt') as stream:
        stream.write(key_id)

    path = os.path.join(dir, 'node_address')
    with open(path, 'wt') as stream:
        stream.write(address)


if __name__ == '__main__':
    main()
