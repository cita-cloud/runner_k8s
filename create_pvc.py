#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# pylint: disable=missing-docstring

import argparse
import os
import yaml

def parse_arguments():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(
        dest='subcmd', title='subcommands', help='additional help')

    #
    # Subcommand: local_pvc
    #

    plocal_pvc = subparsers.add_parser(
        SUBCMD_LOCAL_PVC, help='Create pv/pvc base on hostpath.')
    
    plocal_pvc.add_argument(
        '--data_dir', default='/home/docker/cita-cloud-datadir', help='Root data dir where store data of each node.')

    plocal_pvc.add_argument(
            '--node_list', default='minikube', help='Host name list of nodes of k8s cluster.')

    #
    # Subcommand: nfs_pvc
    #

    pnfs_pvc = subparsers.add_parser(
        SUBCMD_NFS_PVC, help='Create pv/pvc base on nfs.')
    
    pnfs_pvc.add_argument(
        '--nfs_server', help='Address of nfs server.')

    pnfs_pvc.add_argument(
        '--nfs_path', help='Path of nfs server.')

    args = parser.parse_args()
    return args


def run_subcmd_local_pvc(args, work_dir):
    node_list = args.node_list.split(',')

    k8s_config = []
    storage_class = {
        'kind': 'StorageClass',
        'apiVersion': 'storage.k8s.io/v1',
        'metadata': {
            'name': 'local-storage',
        },
        'provisioner': 'kubernetes.io/no-provisioner',
        'volumeBindingMode': 'WaitForFirstConsumer',
    }
    k8s_config.append(storage_class)
    local_pv = {
        'apiVersion': 'v1',
        'kind': 'PersistentVolume',
        'metadata': {
            'name': 'local-pv',
        },
        'spec': {
            'capacity': {
                'storage': '100Gi',
            },
            'accessModes': [
                'ReadWriteMany',
            ],
            'persistentVolumeReclaimPolicy': 'Retain',
            'storageClassName': 'local-storage',
            'local': {
                'path': args.data_dir,
            },
            'nodeAffinity': {
                'required': {
                    'nodeSelectorTerms': [
                        {
                            'matchExpressions': [
                                {
                                    'key': 'kubernetes.io/hostname',
                                    'operator': 'In',
                                    'values': node_list
                                },
                            ],
                        },
                    ],
                },
            },
        },
    }
    k8s_config.append(local_pv)
    local_pvc = {
        'kind': 'PersistentVolumeClaim',
        'apiVersion': 'v1',
        'metadata': {
            'name': 'local-pvc',
        },
        'spec': {
            'accessModes': [
                'ReadWriteMany',
            ],
            'resources': {
                'requests': {
                    'storage': '10Gi',
                },
            },
            'storageClassName': 'local-storage',
        },
    }
    k8s_config.append(local_pvc)

    # write k8s_config to yaml file
    yaml_ptah = os.path.join(work_dir, 'local-pvc.yaml')
    print("yaml_ptah:{}", yaml_ptah)
    with open(yaml_ptah, 'wt') as stream:
        yaml.dump_all(k8s_config, stream, sort_keys=False)

    print("Done!!!")


def run_subcmd_nfs_pvc(args, work_dir):
    k8s_config = []
    nfs_pv = {
        'apiVersion': 'v1',
        'kind': 'PersistentVolume',
        'metadata': {
            'name': 'nfs-pv',
        },
        'spec': {
            'capacity': {
                'storage': '100Gi',
            },
            'accessModes': [
                'ReadWriteMany',
            ],
            'persistentVolumeReclaimPolicy': 'Retain',
            'nfs': {
                'server': args.nfs_server,
                'path': args.nfs_path,
            },
        },
    }
    k8s_config.append(nfs_pv)
    nfs_pvc = {
        'kind': 'PersistentVolumeClaim',
        'apiVersion': 'v1',
        'metadata': {
            'name': 'nfs-pvc',
        },
        'spec': {
            'accessModes': [
                'ReadWriteMany',
            ],
            'resources': {
                'requests': {
                    'storage': '10Gi',
                },
            },
        },
    }
    k8s_config.append(nfs_pvc)

    # write k8s_config to yaml file
    yaml_ptah = os.path.join(work_dir, 'nfs-pvc.yaml')
    print("yaml_ptah:{}", yaml_ptah)
    with open(yaml_ptah, 'wt') as stream:
        yaml.dump_all(k8s_config, stream, sort_keys=False)

    print("Done!!!")


def main():
    args = parse_arguments()
    print("args:", args)
    funcs_router = {
        SUBCMD_LOCAL_PVC: run_subcmd_local_pvc,
        SUBCMD_NFS_PVC: run_subcmd_nfs_pvc,
    }
    work_dir = os.path.abspath(os.curdir)
    funcs_router[args.subcmd](args, work_dir)


if __name__ == '__main__':
    SUBCMD_LOCAL_PVC = 'local_pvc'
    SUBCMD_NFS_PVC = 'nfs_pvc'
    main()
