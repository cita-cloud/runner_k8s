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

DEFAULT_IMAGEPULLPOLICY = 'Always'

SERVICE_LIST = [
    'network',
    'consensus',
    'executor',
    'storage',
    'controller',
    'kms',
]

SYNCTHING_DOCKER_IMAGE = 'syncthing/syncthing:latest'

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
        '--state_db_user', default='citacloud', help='User of state db.')

    plocal_cluster.add_argument(
        '--state_db_password', default='citacloud', help='Password of state db.')

    plocal_cluster.add_argument(
        '--service_config', default='service-config.toml', help='Config file about service information.')

    plocal_cluster.add_argument(
        '--node_port',
        type=int,
        default=30004,
        help='The node port of rpc.')

    plocal_cluster.add_argument(
        '--need_monitor',
        type=bool,
        default=False,
        help='Is need monitor')

    plocal_cluster.add_argument(
        '--pvc_name', help='Name of persistentVolumeClaim.')

    #
    # Subcommand: multi_cluster
    #

    pmulti_cluster = subparsers.add_parser(
        SUBCMD_MULTI_CLUSTER, help='Create a chain in multi cluster.')

    pmulti_cluster.add_argument(
        '--block_delay_number',
        type=int,
        default=0,
        help='The block delay number of chain.')
    
    pmulti_cluster.add_argument(
        '--chain_name', default='test-chain', help='The name of chain.')
    
    pmulti_cluster.add_argument(
        '--service_config', default='service-config.toml', help='Config file about service information.')

    pmulti_cluster.add_argument(
        '--need_monitor',
        type=bool,
        default=False,
        help='Is need monitor')
    
    pmulti_cluster.add_argument(
        '--timestamp',
        type=int,
        help='Timestamp of genesis block.')

    pmulti_cluster.add_argument(
        '--super_admin',
        help='Address of super admin.')

    pmulti_cluster.add_argument(
        '--authorities',
        help='Authorities (addresses) list.')

    pmulti_cluster.add_argument(
        '--nodes',
        help='Node network ip list.')
    
    pmulti_cluster.add_argument(
        '--lbs_tokens',
        help='The token list of LBS.')
    
    pmulti_cluster.add_argument(
        '--sync_device_ids',
        help='Device id list of syncthings.')

    pmulti_cluster.add_argument(
        '--kms_passwords', help='Password list of kms.')

    pmulti_cluster.add_argument(
        '--node_ports',
        help='The list of start port of Nodeport.')

    pmulti_cluster.add_argument(
        '--pvc_names', help='The list of persistentVolumeClaim names.')

    pmulti_cluster.add_argument(
        '--state_db_user', default='citacloud', help='User of state db.')

    pmulti_cluster.add_argument(
        '--state_db_password', default='citacloud', help='Password of state db.')

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


def gen_kms_account(dir, kms_docker_image):
    cmd = 'docker run --rm -e PUID=$(id -u $USER) -e PGID=$(id -g $USER) -v {0}:{0} -w {0} {1} kms create -k key_file'.format(dir, kms_docker_image)
    kms_create = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = kms_create.stdout.readlines()[-1].decode().strip()
    print("kms create output:", output)
    # output should looks like: key_id:1,address:0xba21324990a2feb0a0b6ca16b444b5585b841df9
    infos = output.split(',')
    key_id = infos[0].split(':')[1]
    address = infos[1].split(':')[1]

    path = os.path.join(dir, 'key_id')
    with open(path, 'wt') as stream:
        stream.write(key_id)

    path = os.path.join(dir, 'node_address')
    with open(path, 'wt') as stream:
        stream.write(address)

    return address


def gen_super_admin(work_dir, chain_name, kms_docker_image, kms_password):
    path = os.path.join(work_dir, 'cita-cloud/{}/key_file'.format(chain_name))
    with open(path, 'wt') as stream:
        stream.write(kms_password)
    super_admin = gen_kms_account("{0}/cita-cloud/{1}".format(work_dir, chain_name), kms_docker_image)
    # clean key_file
    os.remove(path)
    return super_admin


def gen_authorities(work_dir, chain_name, kms_docker_image, kms_password, peers_count):
    for i in range(peers_count):
        path = os.path.join("{0}/cita-cloud/{1}/node{2}".format(work_dir, chain_name, i), 'key_file')
        with open(path, 'wt') as stream:
            stream.write(kms_password)
    
    authorities = []
    for i in range(peers_count):
        path = "{0}/cita-cloud/{1}/node{2}".format(work_dir, chain_name, i)
        addr = gen_kms_account(path, kms_docker_image)
        authorities.append(addr)
    
    # clean key_file for peers
    for i in range(peers_count):
        path = os.path.join("{0}/cita-cloud/{1}/node{2}".format(work_dir, chain_name, i), 'key_file')
        os.remove(path)
    
    return authorities


INIT_SYSCONFIG_TEMPLATE = '''version = 0
chain_id = \"0x0000000000000000000000000000000000000000000000000000000000000001\"
admin = \"0x010928818c840630a60b4fda06848cac541599462f\"
block_interval = 3
validators = [\"0x010928818c840630a60b4fda06848cac541599462f\"]
'''


def gen_init_sysconfig(work_dir, chain_name, super_admin, authorities, peers_count):
    init_sys_config = toml.loads(INIT_SYSCONFIG_TEMPLATE)
    init_sys_config['block_interval'] = DEFAULT_BLOCK_INTERVAL
    init_sys_config['validators'] = authorities    
    init_sys_config['admin'] = super_admin

    # write init_sys_config.toml into peers
    for i in range(peers_count):
        path = os.path.join("{0}/cita-cloud/{1}/node{2}".format(work_dir, chain_name, i), 'init_sys_config.toml')
        with open(path, 'wt') as stream:
            toml.dump(init_sys_config, stream)


# generate sync peers info by pod name
def gen_sync_peers(work_dir, count, chain_name):
    mark_str = 'Device ID: '
    device_id_len = 63
    peers = []
    for i in range(count):
        cmd = 'docker run --rm -e PUID=$(id -u $USER) -e PGID=$(id -g $USER) -v {0}:{0} {1} -generate="{0}/cita-cloud/{2}/node{3}/config"'.format(work_dir, SYNCTHING_DOCKER_IMAGE, chain_name, i)
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

        path = os.path.join(work_dir, 'cita-cloud/{}/node{}/config'.format(chain_name, i))
        need_directory(path)

        config_example.write(os.path.join(work_dir, 'cita-cloud/{}/node{}/config/config.xml'.format(chain_name, i)))


def gen_kms_secret(kms_password, secret_name):
    bpwd = bytes(kms_password, encoding='utf8')
    b64pwd = base64.b64encode(bpwd)
    b64pwd_str = b64pwd.decode('utf-8')
    secret = {
        'apiVersion': 'v1',
        'kind': 'Secret',
        'metadata': {
            'name': secret_name,
        },
        'type': 'Opaque',
        'data': {
            'key_file': b64pwd_str
        }
    }
    return secret


def gen_grpc_service(chain_name, node_port):
    grpc_service = {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {
            'name': '{}-node-port'.format(chain_name)
        },
        'spec': {
            'type': 'NodePort',
            'ports': [
                {
                    'port': 50004,
                    'targetPort': 50004,
                    'nodePort': node_port,
                    'name': 'rpc',
                },
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
                }
            ],
            'selector': {
                'node_name': get_node_pod_name(i, chain_name)
            }
        }
    }
    return network_service

def gen_monitor_service(i, chain_name, node_port):
    monitor_service = {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {
            'name': 'monitor-{}-{}'.format(chain_name, i)
        },
        'spec': {
            'type': 'NodePort',
            'ports': [
                {
                    'port': 9256,
                    'targetPort': 9256,
                    'nodePort': node_port + 1 + 5 * i,
                    'name': 'process',
                },
                {
                    'port': 9349,
                    'targetPort': 9349,
                    'nodePort': node_port + 1 + 5 * i + 1,
                    'name': 'exporter',
                },
            ],
            'selector': {
                'node_name': get_node_pod_name(i, chain_name)
            }
        }
    }
    return monitor_service

def gen_executor_service(i, chain_name, node_port, is_chaincode_executor):
    executor_service = {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {
            'name': 'executor-{}-{}'.format(chain_name, i)
        },
        'spec': {
            'type': 'NodePort',
            'ports': [
                {
                    'port': 50002,
                    'targetPort': 50002,
                    'nodePort': node_port + 1 + 5 * i + 4,
                    'name': 'call',
                },
            ],
            'selector': {
                'node_name': get_node_pod_name(i, chain_name)
            }
        }
    }
    if is_chaincode_executor:
        chaincode_port = {
            'port': 7052,
            'targetPort': 7052,
            'nodePort': node_port + 1 + 5 * i + 2,
            'name': 'chaincode',
        }
        eventhub_port = {
            'port': 7053,
            'targetPort': 7053,
            'nodePort': node_port + 1 + 5 * i + 3,
            'name': 'eventhub',
        }
        executor_service['spec']['ports'].append(chaincode_port)
        executor_service['spec']['ports'].append(eventhub_port)
    return executor_service


def gen_node_pod(i, service_config, chain_name, pvc_name, state_db_user, state_db_password, is_need_monitor, kms_secret_name):
    containers = []
    syncthing_container = {
        'image': SYNCTHING_DOCKER_IMAGE,
        'imagePullPolicy': DEFAULT_IMAGEPULLPOLICY,
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
                'subPath': 'cita-cloud/{}/node{}'.format(chain_name, i),
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
    containers.append(syncthing_container)
    for service in service_config['services']:
        if service['name'] == 'network':
            network_container = {
                'image': service['docker_image'],
                'imagePullPolicy': DEFAULT_IMAGEPULLPOLICY,
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
                        'subPath': 'cita-cloud/{}/node{}'.format(chain_name, i),
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
                'imagePullPolicy': DEFAULT_IMAGEPULLPOLICY,
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
                        'subPath': 'cita-cloud/{}/node{}'.format(chain_name, i),
                        'mountPath': '/data',
                    },
                ],
            }
            containers.append(consensus_container)
        elif service['name'] == 'executor':
            executor_container = {
                'image': service['docker_image'],
                'imagePullPolicy': DEFAULT_IMAGEPULLPOLICY,
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
                        'subPath': 'cita-cloud/{}/node{}'.format(chain_name, i),
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
                eventhub_port = {
                    'containerPort': 7053,
                    'protocol': 'TCP',
                    'name': 'eventhub',
                }
                executor_container['ports'].append(eventhub_port)
                if "chaincode_ext" in service['docker_image']:
                    state_db_container = {
                        'image': "couchdb",
                        'imagePullPolicy': DEFAULT_IMAGEPULLPOLICY,
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
                                'name': 'datadir',
                                'subPath': 'cita-cloud/{}/node{}/state-data'.format(chain_name, i),
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
                'imagePullPolicy': DEFAULT_IMAGEPULLPOLICY,
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
                        'subPath': 'cita-cloud/{}/node{}'.format(chain_name, i),
                        'mountPath': '/data',
                    },
                ],
            }
            containers.append(storage_container)
        elif service['name'] == 'controller':
            controller_container = {
                'image': service['docker_image'],
                'imagePullPolicy': DEFAULT_IMAGEPULLPOLICY,
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
                        'subPath': 'cita-cloud/{}/node{}'.format(chain_name, i),
                        'mountPath': '/data',
                    },
                ],
            }
            containers.append(controller_container)
        elif service['name'] == 'kms':
            kms_container = {
                'image': service['docker_image'],
                'imagePullPolicy': DEFAULT_IMAGEPULLPOLICY,
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
                        'subPath': 'cita-cloud/{}/node{}'.format(chain_name, i),
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

    if is_need_monitor:
        monitor_process_container = {
            'image': 'citacloud/monitor-process-exporter:0.4.0',
            'imagePullPolicy': DEFAULT_IMAGEPULLPOLICY,
            'name': 'monitor-process',
            'ports': [
                {
                    'containerPort': 9256,
                    'protocol': 'TCP',
                    'name': 'process',
                }
            ],
            'args': [
                '--procfs',
                '/proc',
                '--config.path',
                '/config/process_list.yml'
            ],
            'workingDir': '/data',
            'volumeMounts': [
                {
                    'name': 'datadir',
                    'subPath': 'cita-cloud/{}/node{}'.format(chain_name, i),
                    'mountPath': '/data',
                },
            ],
        }
        containers.append(monitor_process_container)
        monitor_citacloud_container = {
            'image': 'citacloud/monitor-citacloud-exporter:0.1.0',
            'imagePullPolicy': DEFAULT_IMAGEPULLPOLICY,
            'name': 'monitor-citacloud',
            'ports': [
                {
                    'containerPort': 9349,
                    'protocol': 'TCP',
                    'name': 'exporter',
                }
            ],
            'args': [
                "--node-grpc-host",
                "localhost",
                "--node-grpc-port",
                "50004",
                "--node-data-folder",
                ".",
            ],
            'workingDir': '/data',
            'volumeMounts': [
                {
                    'name': 'datadir',
                    'subPath': 'cita-cloud/{}/node{}'.format(chain_name, i),
                    'mountPath': '/data',
                },
            ],
        }
        containers.append(monitor_citacloud_container)

    volumes = [
        {
            'name': 'kms-key',
            'secret': {
                'secretName': kms_secret_name
            }
        },
        {
            'name': 'network-key',
            'secret': {
                'secretName': 'node{}-network-secret'.format(i)
            }
        },
        {
            'name': 'datadir',
            'persistentVolumeClaim': {
                'claimName': pvc_name,
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
            'shareProcessNamespace': True,
            'containers': containers,
            'volumes': volumes,
        }
    }
    return pod


def find_docker_image(service_config, service_name):
    for service in service_config['services']:
        if service['name'] == service_name:
            return service['docker_image']


def load_service_config(work_dir, service_config):
    service_config_path = os.path.join(work_dir, service_config)
    return toml.load(service_config_path)


def verify_service_config(service_config):
    indexs = 1
    for service in service_config['services']:
        index = (SERVICE_LIST.index(service['name']) + 1) * 10
        indexs *= index

    if indexs != 10 * 20 * 30 * 40 * 50 * 60:
        print('There must be 6 services:', SERVICE_LIST)
        sys.exit(1)


def run_subcmd_local_cluster(args, work_dir):
    if not args.kms_password:
        print('kms_password must be set!')
        sys.exit(1)

    if not args.pvc_name:
        print('pvc_name must be set!')
        sys.exit(1)

    # load service_config
    service_config = load_service_config(work_dir, args.service_config)
    print("service_config:", service_config)

    # verify service_config
    verify_service_config(service_config)

    # generate peers info by pod name
    peers = gen_peers(args.peers_count, args.chain_name)
    print("peers:", peers)

    # generate network config for all peers
    net_config_list = gen_net_config_list(peers)
    print("net_config_list:", net_config_list)

    # generate node config
    timestamp = int(time.time() * 1000)
    for index, net_config in enumerate(net_config_list):
        node_path = os.path.join(work_dir, 'cita-cloud/{}/node{}'.format(args.chain_name, index))
        need_directory(node_path)
        tx_infos_path = os.path.join(work_dir, 'cita-cloud/{}/node{}/tx_infos'.format(args.chain_name, index))
        need_directory(tx_infos_path)
        # generate network config file
        net_config_file = os.path.join(node_path, 'network-config.toml')
        with open(net_config_file, 'wt') as stream:
            toml.dump(net_config, stream)
        # generate log config
        gen_log4rs_config(node_path)
        gen_consensus_config(node_path, index)
        gen_controller_config(node_path, args.block_delay_number)
        # generate genesis
        gen_genesis(node_path, timestamp, DEFAULT_PREVHASH)


    # generate init_sys_config
    kms_docker_image = find_docker_image(service_config, "kms")
    super_admin = gen_super_admin(work_dir, args.chain_name, kms_docker_image, args.kms_password)
    authorities = gen_authorities(work_dir, args.chain_name, kms_docker_image, args.kms_password, args.peers_count)
    gen_init_sysconfig(work_dir, args.chain_name, super_admin, authorities, args.peers_count)

    # generate syncthing config
    sync_peers = gen_sync_peers(work_dir, args.peers_count, args.chain_name)
    print("sync_peers:", sync_peers)
    gen_sync_configs(work_dir, sync_peers, args.chain_name)

    # is chaincode executor
    executor_docker_image = find_docker_image(service_config, "executor")
    is_chaincode_executor = "chaincode" in executor_docker_image

    # generate k8s yaml
    k8s_config = []
    kms_secret = gen_kms_secret(args.kms_password, 'kms-secret')
    k8s_config.append(kms_secret)
    grpc_service = gen_grpc_service(args.chain_name, args.node_port)
    k8s_config.append(grpc_service)
    for i in range(args.peers_count):
        netwok_secret = gen_network_secret(i)
        k8s_config.append(netwok_secret)
        network_service = gen_network_service(i, args.chain_name)
        k8s_config.append(network_service)
        pod = gen_node_pod(i, service_config, args.chain_name, args.pvc_name, args.state_db_user, args.state_db_password, args.need_monitor, 'kms-secret')
        k8s_config.append(pod)
        if args.need_monitor:
            monitor_service = gen_monitor_service(i, args.chain_name, args.node_port)
            k8s_config.append(monitor_service)
        executor_service = gen_executor_service(i, args.chain_name, args.node_port, is_chaincode_executor)
        k8s_config.append(executor_service)

    # write k8s_config to yaml file
    yaml_ptah = os.path.join(work_dir, '{}.yaml'.format(args.chain_name))
    print("yaml_ptah:{}", yaml_ptah)
    with open(yaml_ptah, 'wt') as stream:
        yaml.dump_all(k8s_config, stream, sort_keys=False)

    print("Done!!!")


# multi cluster
def gen_peers_net_addr(nodes, node_ports):
    return list(map(lambda ip, port: {'ip': ip, 'port': port}, nodes, node_ports))


def gen_sync_peers_mc(nodes, node_ports, sync_device_ids):
    return list(map(lambda ip, port, device_id: {'ip': ip, 'port': port + 1, 'device_id': device_id}, nodes, node_ports, sync_device_ids))


def gen_all_service(i, chain_name, node_port, token):
    all_service = {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {
            'annotations': {
                'service.beta.kubernetes.io/alibaba-cloud-loadbalancer-id': token,
                'service.beta.kubernetes.io/alicloud-loadbalancer-force-override-listeners': 'true',
            },
            'name': 'all-{}-{}'.format(chain_name, i)
        },
        'spec': {
            'type': 'LoadBalancer',
            'ports': [
                {
                    'port': 40000,
                    'targetPort': 40000,
                    'nodePort': node_port,
                    'name': 'network',
                },
                {
                    'port': 22000,
                    'targetPort': 22000,
                    'nodePort': node_port + 1,
                    'name': 'sync',
                },
                {
                    'port': 50004,
                    'targetPort': 50004,
                    'nodePort': node_port + 2,
                    'name': 'rpc',
                },
                {
                    'port': 9256,
                    'targetPort': 9256,
                    'nodePort': node_port + 3,
                    'name': 'process',
                },
                {
                    'port': 9349,
                    'targetPort': 9349,
                    'nodePort': node_port + 4,
                    'name': 'exporter',
                },
                {
                    'port': 50002,
                    'targetPort': 50002,
                    'nodePort': node_port + 5,
                    'name': 'call',
                },
                {
                    'port': 7052,
                    'targetPort': 7052,
                    'nodePort': node_port + 6,
                    'name': 'chaincode',
                },
                {
                    'port': 7053,
                    'targetPort': 7053,
                    'nodePort': node_port + 7,
                    'name': 'eventhub',
                },
            ],
            'selector': {
                'node_name': get_node_pod_name(i, chain_name)
            }
        }
    }
    return all_service


def run_subcmd_multi_cluster(args, work_dir):
    # load service_config
    service_config = load_service_config(work_dir, args.service_config)
    print("service_config:", service_config)

    # verify service_config
    verify_service_config(service_config)
    
    # parse and check arguments
    if not args.super_admin:
        print('Need super admin.')
        sys.exit(1)
    nodes = args.nodes.split(',')
    lbs_tokens = args.lbs_tokens.split(',')
    authorities = args.authorities.split(',')
    sync_device_ids = args.sync_device_ids.split(',')
    kms_passwords = args.kms_passwords.split(',')
    node_ports = list(map(lambda x : int(x), args.node_ports.split(',')))
    pvc_names = args.pvc_names.split(',')

    peers_count = len(nodes)
    if len(lbs_tokens) != peers_count:
        print('The len of lbs_tokens is invalid')
        sys.exit(1)

    if len(authorities) != peers_count:
        print('The len of authorities is invalid')
        sys.exit(1)
    
    if len(sync_device_ids) != peers_count:
        print('The len of sync_device_ids is invalid')
        sys.exit(1)

    if len(kms_passwords) != peers_count:
        print('The len of kms_passwords is invalid')
        sys.exit(1)

    if len(node_ports) != peers_count:
        print('The len of node_ports is invalid')
        sys.exit(1)
    
    if len(pvc_names) != peers_count:
        print('The len of pvc_names is invalid')
        sys.exit(1)

    # generate peers info by pod name
    peers = gen_peers_net_addr(nodes, node_ports)
    print("peers:", peers)

    # generate network config for all peers
    net_config_list = gen_net_config_list(peers)
    print("net_config_list:", net_config_list)

    # generate node config
    if args.timestamp:
        timestamp = args.timestamp
    else:
        timestamp = int(time.time() * 1000)
    for index, net_config in enumerate(net_config_list):
        node_path = os.path.join(work_dir, 'cita-cloud/{}/node{}'.format(args.chain_name, index))
        need_directory(node_path)
        tx_infos_path = os.path.join(work_dir, 'cita-cloud/{}/node{}/tx_infos'.format(args.chain_name, index))
        need_directory(tx_infos_path)
        # generate network config file
        net_config_file = os.path.join(node_path, 'network-config.toml')
        with open(net_config_file, 'wt') as stream:
            toml.dump(net_config, stream)
        # generate log config
        gen_log4rs_config(node_path)
        gen_consensus_config(node_path, index)
        gen_controller_config(node_path, args.block_delay_number)
        # generate genesis
        gen_genesis(node_path, timestamp, DEFAULT_PREVHASH)

    # generate init_sys_config
    gen_init_sysconfig(work_dir, args.chain_name, args.super_admin, authorities, peers_count)
    
    # generate syncthing config
    sync_peers = gen_sync_peers_mc(nodes, node_ports, sync_device_ids)
    print("sync_peers:", sync_peers)
    gen_sync_configs(work_dir, sync_peers, args.chain_name)

    # generate k8s yaml
    for i in range(peers_count):
        k8s_config = []
        kms_secret = gen_kms_secret(kms_passwords[i], 'kms-secret-{}'.format(i))
        k8s_config.append(kms_secret)
        netwok_secret = gen_network_secret(i)
        k8s_config.append(netwok_secret)
        pod = gen_node_pod(i, service_config, args.chain_name, pvc_names[i], args.state_db_user, args.state_db_password, args.need_monitor, 'kms-secret-{}'.format(i))
        k8s_config.append(pod)
        all_service = gen_all_service(i, args.chain_name, node_ports[i], lbs_tokens[i])
        k8s_config.append(all_service)
        # write k8s_config to yaml file
        yaml_ptah = os.path.join(work_dir, '{}-{}.yaml'.format(args.chain_name, i))
        print("yaml_ptah:{}", yaml_ptah)
        with open(yaml_ptah, 'wt') as stream:
            yaml.dump_all(k8s_config, stream, sort_keys=False)

    print("Done!!!")


def main():
    args = parse_arguments()
    print("args:", args)
    funcs_router = {
        SUBCMD_LOCAL_CLUSTER: run_subcmd_local_cluster,
        SUBCMD_MULTI_CLUSTER: run_subcmd_multi_cluster,
    }
    work_dir = os.path.abspath(os.curdir)
    funcs_router[args.subcmd](args, work_dir)


if __name__ == '__main__':
    SUBCMD_LOCAL_CLUSTER = 'local_cluster'
    SUBCMD_MULTI_CLUSTER = 'multi_cluster'
    main()