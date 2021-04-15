#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# pylint: disable=missing-docstring

import os
import subprocess
import shutil

def main():
    cmd = 'syncthing -generate=node_config'
    syncthing_gen = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    mark_str = 'Device ID: '
    device_id_len = 63
    output = str(syncthing_gen.stdout.read())
    mark_index = output.index(mark_str)
    device_id = output[mark_index + len(mark_str):mark_index + len(mark_str) + device_id_len]
    print("device_id:", device_id)
    
    current_dir = os.path.abspath(os.curdir)
    dir = os.path.join(current_dir, 'node_config')
    target_dir = os.path.join(current_dir, device_id)

    shutil.move(dir, target_dir)

    config_path = os.path.join(target_dir, 'config.xml')
    os.remove(config_path)


if __name__ == '__main__':
    main()
