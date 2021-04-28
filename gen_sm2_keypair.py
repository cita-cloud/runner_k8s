#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# pylint: disable=missing-docstring

import os
from pysmx.SM2 import generate_keypair
from pysmx.SM3 import hash_msg


def gen_sm2_keypair(work_dir, chain_name):
    pk, sk = generate_keypair()
    addr = '0x'+hash_msg(pk)[24:]
    path = os.path.join(work_dir, 'cita-cloud/{}/node_key'.format(chain_name))
    with open(path, 'wt') as stream:
        stream.write('0x'+sk.hex())
    path = os.path.join(work_dir, 'cita-cloud/{}/node_address'.format(chain_name))
    with open(path, 'wt') as stream:
        stream.write(addr)
    return addr


def main():
    pk, sk = generate_keypair()
    address = '0x'+hash_msg(pk)[24:]

    print("address:", address)

    current_dir = os.path.abspath(os.curdir)
    target_dir = os.path.join(current_dir, address)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    path = os.path.join(target_dir, 'node_key')
    with open(path, 'wt') as stream:
        stream.write('0x'+sk.hex())

    path = os.path.join(target_dir, 'node_address')
    with open(path, 'wt') as stream:
        stream.write(address)
    
    path = os.path.join(target_dir, 'key_id')
    with open(path, 'wt') as stream:
        stream.write("1")


if __name__ == '__main__':
    main()
