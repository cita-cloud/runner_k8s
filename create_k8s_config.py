#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# pylint: disable=missing-docstring

import argparse
import os
import sys
import toml
import subprocess
import time
import copy
import xml.etree.ElementTree as ET
import base64
import yaml

DEFAULT_PREVHASH = '0x{:064x}'.format(0)

DEFAULT_BLOCK_INTERVAL = 6

SERVICE_LIST = [
    'network',
    'consensus',
    'executor',
    'storage',
    'controller',
    'kms',
]

SYNCTHING_DOCKER_IMAGE = 'syncthing/syncthing:1.13'

SYNC_FOLDERS = [
    'blocks',
    'proposals',
    'txs'
]


def parse_arguments():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(
        dest='subcmd', title='subcommands', help='additional help')

    #
    # Subcommand: local_cluster
    #

    plocal_cluster = subparsers.add_parser(
        SUBCMD_LOCAL_CLUSTER, help='Create a chain in local cluster.')

    plocal_cluster.add_argument(
        '--block_delay_number',
        type=int,
        default=0,
        help='The block delay number of chain.')

    plocal_cluster.add_argument(
        '--chain_name', default='test-chain', help='The name of chain.')

    plocal_cluster.add_argument(
        '--peers_count',
        type=int,
        default=2,
        help='Count of peers.')

    plocal_cluster.add_argument(
        '--kms_password', help='Password of kms.')

    plocal_cluster.add_argument(
        '--state_db_user', help='User of state db.')

    plocal_cluster.add_argument(
        '--state_db_password', help='Password of state db.')

    plocal_cluster.add_argument(
        '--service_config', default='service-config.toml', help='Config file about service information.')

    plocal_cluster.add_argument(
        '--data_dir', default='/home/docker/cita-cloud-datadir', help='Root data dir where store data of each node.')

    args = parser.parse_args()

    return args


# pod name is {chain_name}-{index}
def get_node_pod_name(index, chain_name):
    return '{}-{}'.format(chain_name, index)


# generate peers info by pod name
def gen_peers(count, chain_name):
    peers = []
    for i in range(count):
        peer = {
            'ip': get_node_pod_name(i, chain_name),
            'port': 40000
        }
        peers.append(peer)
    return peers


def gen_net_config_list(peers):
    net_config_list = []
    for peer in peers:
        peers_clone = copy.deepcopy(peers)
        peers_clone.remove(peer)
        net_config = {
            'port': peer['port'],
            'peers': peers_clone
        }
        net_config_list.append(net_config)
    return net_config_list


def need_directory(path):
    """Create a directory if it is not existed."""
    if not os.path.exists(path):
        os.makedirs(path)


LOG_CONFIG_TEMPLATE = '''# Scan this file for changes every 30 seconds
refresh_rate: 30 seconds

appenders:
  # An appender named \"stdout\" that writes to stdout
  stdout:
    kind: console

  journey-service:
    kind: rolling_file
    path: \"logs/{0}-service.log\"
    policy:
      # Identifies which policy is to be used. If no kind is specified, it will
      # default to \"compound\".
      kind: compound
      # The remainder of the configuration is passed along to the policy's
      # deserializer, and will vary based on the kind of policy.
      trigger:
        kind: size
        limit: 1mb
      roller:
        kind: fixed_window
        base: 1
        count: 5
        pattern: \"logs/{0}-service.{{}}.gz\"

# Set the default logging level and attach the default appender to the root
root:
  level: info
  appenders:
    - journey-service
'''


def gen_log4rs_config(node_path):
    for service_name in SERVICE_LIST:
        path = os.path.join(node_path, '{}-log4rs.yaml'.format(service_name))
        with open(path, 'wt') as stream:
            stream.write(LOG_CONFIG_TEMPLATE.format(service_name))


CONSENSUS_CONFIG_TEMPLATE = '''network_port = 50000
controller_port = 50004
node_id = {}
'''


# generate consensus-config.toml
def gen_consensus_config(node_path, i):
    path = os.path.join(node_path, 'consensus-config.toml')
    with open(path, 'wt') as stream:
        stream.write(CONSENSUS_CONFIG_TEMPLATE.format(i))


CONTROLLER_CONFIG_TEMPLATE = '''network_port = 50000
consensus_port = 50001
storage_port = 50003
kms_port = 50005
executor_port = 50002
block_delay_number = {}
'''


# generate controller-config.toml
def gen_controller_config(node_path, block_delay_number):
    path = os.path.join(node_path, 'controller-config.toml')
    with open(path, 'wt') as stream:
        stream.write(CONTROLLER_CONFIG_TEMPLATE.format(block_delay_number))


GENESIS_TEMPLATE = '''timestamp = {}
prevhash = \"{}\"
'''


def gen_genesis(node_path, timestamp, prevhash):
    path = os.path.join(node_path, 'genesis.toml')
    with open(path, 'wt') as stream:
        stream.write(GENESIS_TEMPLATE.format(timestamp, prevhash))


INIT_SYSCONFIG_TEMPLATE = '''version = 0
chain_id = \"0x0000000000000000000000000000000000000000000000000000000000000001\"
admin = \"0x010928818c840630a60b4fda06848cac541599462f\"
block_interval = 3
validators = [\"0x010928818c840630a60b4fda06848cac541599462f\"]
'''


def gen_init_sysconfig(node_path, peers_count):
    init_sys_config = toml.loads(INIT_SYSCONFIG_TEMPLATE)
    init_sys_config['validators'] *= peers_count
    init_sys_config['block_interval'] = DEFAULT_BLOCK_INTERVAL
    path = os.path.join(node_path, 'init_sys_config.toml')
    with open(path, 'wt') as stream:
        toml.dump(init_sys_config, stream)


# generate sync peers info by pod name
def gen_sync_peers(work_dir, count, chain_name):
    mark_str = 'Device ID: '
    device_id_len = 63
    peers = []
    for i in range(count):
        cmd = 'docker run --rm -e PUID=$(id -u $USER) -e PGID=$(id -g $USER) -v {0}:{0} {1} -generate="{0}/node{2}/config"'.format(work_dir, SYNCTHING_DOCKER_IMAGE, i)
        syncthing_gen = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = str(syncthing_gen.stdout.read())
        mark_index = output.index(mark_str)
        device_id = output[mark_index + len(mark_str):mark_index + len(mark_str) + device_id_len]
        print("device_id:", device_id)
        peer = {
            'ip': get_node_pod_name(i, chain_name),
            'port': 22000,
            'device_id': device_id
        }
        peers.append(peer)
    return peers


def gen_sync_configs(work_dir, sync_peers, chain_name):
    for i in range(len(sync_peers)):
        config_example = ET.parse(os.path.join(work_dir, 'config.xml'))
        root = config_example.getroot()
        # add device for all folder
        for elem in root.findall('folder'):
            for peer in sync_peers:
                d = ET.SubElement(elem, 'device')
                d.set('id', peer['device_id'])
                d.set('introducedBy', '')
        # add all device
        for peer in sync_peers:
            d = ET.SubElement(root, 'device')
            d.set('id', peer['device_id'])
            d.set('name', peer['ip'])
            d.set('compression', 'always')
            d.set('introducer', 'false')
            d.set('skipIntroductionRemovals', 'false')
            d.set('introducedBy', '')
            address = ET.SubElement(d, 'address')
            address.text = 'tcp://{}:{}'.format(peer['ip'], peer['port'])
            paused = ET.SubElement(d, 'paused')
            paused.text = 'false'
            autoAcceptFolders = ET.SubElement(d, 'autoAcceptFolders')
            autoAcceptFolders.text = 'false'
            maxSendKbps = ET.SubElement(d, 'maxSendKbps')
            maxSendKbps.text = '0'
            maxRecvKbps = ET.SubElement(d, 'maxRecvKbps')
            maxRecvKbps.text = '0'
            maxRequestKiB = ET.SubElement(d, 'maxRequestKiB')
            maxRequestKiB.text = '0'
        # add gui/apikey
        gui = root.findall('gui')[0]
        apikey = ET.SubElement(gui, 'apikey')
        apikey.text = chain_name

        config_example.write(os.path.join(work_dir, 'node{}/config/config.xml'.format(i)))


def gen_kms_secret(kms_password):
    bpwd = bytes(kms_password, encoding='utf8')
    b64pwd = base64.b64encode(bpwd)
    b64pwd_str = b64pwd.decode('utf-8')
    secret = {
        'apiVersion': 'v1',
        'kind': 'Secret',
        'metadata': {
            'name': 'kms-secret',
        },
        'type': 'Opaque',
        'data': {
            'key_file': b64pwd_str
        }
    }
    return secret


def gen_grpc_service(chain_name):
    grpc_service = {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {
            'name': '{}-loadbalancer'.format(chain_name)
        },
        'spec': {
            'type': 'LoadBalancer',
            'ports': [
                 {
                     'port': 50004,
                     'targetPort': 50004
                 }
            ],
            'selector': {
                'chain_name': chain_name
            }
        }
    }
    return grpc_service


def gen_network_secret(i):
    network_key = '0x' + os.urandom(32).hex()
    netwok_secret = {
        'apiVersion': 'v1',
        'kind': 'Secret',
        'metadata': {
            'name': 'node{}-network-secret'.format(i),
        },
        'type': 'Opaque',
        'data': {
            'network-key': base64.b64encode(bytes(network_key, encoding='utf8')).decode('utf-8')
        }
    }
    return netwok_secret


def gen_network_service(i, chain_name):
    network_service = {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {
            'name': get_node_pod_name(i, chain_name)
        },
        'spec': {
            'ports': [
                {
                    'port': 40000,
                    'targetPort': 40000,
                    'name': 'network',
                },
                {
                    'port': 22000,
                    'targetPort': 22000,
                    'name': 'syncthing',
                },
                {
                    'port': 8384,
                    'targetPort': 8384,
                    'name': 'gui',
                },
                {
                    'port': 7052,
                    'targetPort': 7052,
                    'name': 'chaincode',
                }
            ],
            'selector': {
                'node_name': get_node_pod_name(i, chain_name)
            }
        }
    }
    return network_service


def gen_node_pod(i, args, service_config):
    chain_name = args.chain_name
    data_dir = args.data_dir
    state_db_user = args.state_db_user
    state_db_password = args.state_db_password
    containers = [
        {
            'image': SYNCTHING_DOCKER_IMAGE,
            'name': 'syncthing',
            'ports': [
                 {
                     'containerPort': 22000,
                     'protocol': 'TCP',
                     'name': 'sync',
                 },
                 {
                     'containerPort': 8384,
                     'protocol': 'TCP',
                     'name': 'gui',
                 }
            ],
            'volumeMounts': [
                {
                    'name': 'datadir',
                    'mountPath': '/var/syncthing',
                }
            ],
            'env': [
                {
                    'name': 'PUID',
                    'value': '0',
                },
                {
                    'name': 'PGID',
                    'value': '0',
                },
            ]
        }
    ]
    for service in service_config['services']:
        if service['name'] == 'network':
            network_container = {
                'image': service['docker_image'],
                'name': service['name'],
                'ports': [
                    {
                        'containerPort': 40000,
                        'protocol': 'TCP',
                        'name': 'network',
                    },
                    {
                        'containerPort': 50000,
                        'protocol': 'TCP',
                        'name': 'grpc',
                    }
                ],
                'command': [
                    'sh',
                    '-c',
                    service['cmd'],
                ],
                'workingDir': '/data',
                'volumeMounts': [
                    {
                        'name': 'datadir',
                        'mountPath': '/data',
                    },
                    {
                        'name': 'network-key',
                        'mountPath': '/network',
                        'readOnly': True,
                    },
                ],
            }
            containers.append(network_container)
        elif service['name'] == 'consensus':
            consensus_container = {
                'image': service['docker_image'],
                'name': service['name'],
                'ports': [
                    {
                        'containerPort': 50001,
                        'protocol': 'TCP',
                        'name': 'grpc',
                    }
                ],
                'command': [
                    'sh',
                    '-c',
                    service['cmd'],
                ],
                'workingDir': '/data',
                'volumeMounts': [
                    {
                        'name': 'datadir',
                        'mountPath': '/data',
                    },
                ],
            }
            containers.append(consensus_container)
        elif service['name'] == 'executor':
            executor_container = {
                'image': service['docker_image'],
                'name': service['name'],
                'ports': [
                    {
                        'containerPort': 50002,
                        'protocol': 'TCP',
                        'name': 'grpc',
                    }
                ],
                'command': [
                    'sh',
                    '-c',
                    service['cmd'],
                ],
                'workingDir': '/data',
                'volumeMounts': [
                    {
                        'name': 'datadir',
                        'mountPath': '/data',
                    },
                ],
            }
            # if executor is chaincode
            # add chaincode_port for executor
            # add chaincode_container
            if "chaincode" in service['docker_image']:
                chaincode_port = {
                    'containerPort': 7052,
                    'protocol': 'TCP',
                    'name': 'chaincode',
                }
                executor_container['ports'].append(chaincode_port)
                if "chaincode_ext" in service['docker_image']:
                    state_db_container = {
                        'image': "couchdb:3.1.1",
                        'name': "couchdb",
                        'ports': [
                            {
                                'containerPort': 5984,
                                'protocol': 'TCP',
                                'name': 'couchdb',
                            }
                        ],
                        'volumeMounts': [
                            {
                                'name': 'state-datadir',
                                'mountPath': '/opt/couchdb/data',
                            },
                        ],
                        'env': [
                            {
                                'name': 'COUCHDB_USER',
                                'value': state_db_user,
                            },
                            {
                                'name': 'COUCHDB_PASSWORD',
                                'value': state_db_password,
                            },
                        ],
                    }
                    containers.append(state_db_container)
                    # add --couchdb-username username --couchdb-password password
                    executor_ext_cmd = service['cmd'] + " --couchdb-username " + state_db_user + " --couchdb-password " + state_db_password
                    executor_container['command'] = [
                        'sh',
                        '-c',
                        executor_ext_cmd,
                    ]
                containers.append(executor_container)
        elif service['name'] == 'storage':
            storage_container = {
                'image': service['docker_image'],
                'name': service['name'],
                'ports': [
                    {
                        'containerPort': 50003,
                        'protocol': 'TCP',
                        'name': 'grpc',
                    }
                ],
                'command': [
                    'sh',
                    '-c',
                    service['cmd'],
                ],
                'workingDir': '/data',
                'volumeMounts': [
                    {
                        'name': 'datadir',
                        'mountPath': '/data',
                    },
                ],
            }
            containers.append(storage_container)
        elif service['name'] == 'controller':
            controller_container = {
                'image': service['docker_image'],
                'name': service['name'],
                'ports': [
                    {
                        'containerPort': 50004,
                        'protocol': 'TCP',
                        'name': 'grpc',
                    }
                ],
                'command': [
                    'sh',
                    '-c',
                    service['cmd'],
                ],
                'workingDir': '/data',
                'volumeMounts': [
                    {
                        'name': 'datadir',
                        'mountPath': '/data',
                    },
                ],
            }
            containers.append(controller_container)
        elif service['name'] == 'kms':
            kms_container = {
                'image': service['docker_image'],
                'name': service['name'],
                'ports': [
                    {
                        'containerPort': 50005,
                        'protocol': 'TCP',
                        'name': 'grpc',
                    }
                ],
                'command': [
                    'sh',
                    '-c',
                    service['cmd'],
                ],
                'workingDir': '/data',
                'volumeMounts': [
                    {
                        'name': 'datadir',
                        'mountPath': '/data',
                    },
                    {
                        'name': 'kms-key',
                        'mountPath': '/kms',
                        'readOnly': True,
                    },
                ],
            }
            containers.append(kms_container)
        else:
            print("unexpected service")
            sys.exit(1)

    volumes = [
        {
            'name': 'datadir',
            'hostPath': {
                'path': '{}/node{}'.format(data_dir, i)
            }
        },
        {
            'name': 'state-datadir',
            'hostPath': {
                'path': '{}/node{}/state-data'.format(data_dir, i)
            }
        },
        {
            'name': 'kms-key',
            'secret': {
                'secretName': 'kms-secret'
            }
        },
        {
            'name': 'network-key',
            'secret': {
                'secretName': 'node{}-network-secret'.format(i)
            }
        },
    ]
    pod = {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': get_node_pod_name(i, chain_name),
            'labels': {
                'node_name': get_node_pod_name(i, chain_name),
                'chain_name': chain_name,
            }
        },
        'spec': {
            'containers': containers,
            'volumes': volumes,
        }
    }
    return pod


def run_subcmd_local_cluster(args, work_dir):
    if not args.kms_password:
        print('kms_password must be set!')
        sys.exit(1)
    service_config_path = os.path.join(work_dir, args.service_config)
    print("service_config_path:", service_config_path)
    service_config = toml.load(service_config_path)
    print("service_config:", service_config)

    # verify service_config
    indexs = 1
    for service in service_config['services']:
        index = (SERVICE_LIST.index(service['name']) + 1) * 10
        indexs *= index

    if indexs != 10 * 20 * 30 * 40 * 50 * 60:
        print('There must be 6 services:', SERVICE_LIST)
        sys.exit(1)

    # generate peers info by pod name
    peers = gen_peers(args.peers_count, args.chain_name)
    print("peers:", peers)

    # generate network config for all peers
    net_config_list = gen_net_config_list(peers)
    print("net_config_list:", net_config_list)

    # generate node config
    timestamp = int(time.time() * 1000)
    for index, net_config in enumerate(net_config_list):
        node_path = os.path.join(work_dir, 'node{}'.format(index))
        need_directory(node_path)
        # generate network config file
        net_config_file = os.path.join(node_path, 'network-config.toml')
        with open(net_config_file, 'wt') as stream:
            toml.dump(net_config, stream)
        # generate log config
        gen_log4rs_config(node_path)
        gen_consensus_config(node_path, index)
        gen_controller_config(node_path, args.block_delay_number)
        gen_genesis(node_path, timestamp, DEFAULT_PREVHASH)
        gen_init_sysconfig(node_path, args.peers_count)

    # generate syncthing config
    sync_peers = gen_sync_peers(work_dir, args.peers_count, args.chain_name)
    print("sync_peers:", sync_peers)
    gen_sync_configs(work_dir, sync_peers, args.chain_name)

    # generate k8s yaml
    k8s_config = []
    kms_secret = gen_kms_secret(args.kms_password)
    k8s_config.append(kms_secret)
    grpc_service = gen_grpc_service(args.chain_name)
    k8s_config.append(grpc_service)
    for i in range(args.peers_count):
        netwok_secret = gen_network_secret(i)
        k8s_config.append(netwok_secret)
        network_service = gen_network_service(i, args.chain_name)
        k8s_config.append(network_service)
        pod = gen_node_pod(i, args, service_config)
        k8s_config.append(pod)
    # write k8s_config to yaml file
    yaml_ptah = os.path.join(work_dir, '{}.yaml'.format(args.chain_name))
    print("yaml_ptah:{}", yaml_ptah)
    with open(yaml_ptah, 'wt') as stream:
        yaml.dump_all(k8s_config, stream, sort_keys=False)

    print("Done!!!")


def main():
    args = parse_arguments()
    print("args:", args)
    funcs_router = {
        SUBCMD_LOCAL_CLUSTER: run_subcmd_local_cluster,
    }
    work_dir = os.path.abspath(os.curdir)
    funcs_router[args.subcmd](args, work_dir)


if __name__ == '__main__':
    SUBCMD_LOCAL_CLUSTER = 'local_cluster'
    main()