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

DEFAULT_PREVHASH = '0x{:064x}'.format(0)

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
        default=6,
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
        '--service_config', default='service-config.toml', help='Config file about service information.')

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
'''


# generate consensus-config.toml
def gen_consensus_config(node_path):
    path = os.path.join(node_path, 'consensus-config.toml')
    with open(path, 'wt') as stream:
        stream.write(CONSENSUS_CONFIG_TEMPLATE)


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
    path = os.path.join(node_path, 'init_sys_config.toml')
    with open(path, 'wt') as stream:
        toml.dump(init_sys_config, stream)


# generate peers info by pod name
def gen_sync_peers(work_dir, count, chain_name):
    mark_str = 'Device ID: '
    device_id_len = 63
    peers = []
    for i in range(count):
        cmd = 'docker run --rm -v {0}:{0} {1} -generate="{0}/node{2}/config"'.format(work_dir, SYNCTHING_DOCKER_IMAGE, i)
        print("cmd:", cmd)
        syncthing_gen = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = str(syncthing_gen.stdout.read())
        print("output:", output)
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


def run_subcmd_local_cluster(args, work_dir):
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
        gen_consensus_config(node_path)
        gen_controller_config(node_path, args.block_delay_number)
        gen_genesis(node_path, timestamp, DEFAULT_PREVHASH)
        gen_init_sysconfig(node_path, args.peers_count)

    # generate syncthing config
    sync_peers = gen_sync_peers(work_dir, args.peers_count, args.chain_name)
    print("sync_peers:", sync_peers)

    for i, peer in enumerate(sync_peers):
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
            address.text = 'quic://{}:{}'.format(peer['ip'], peer['port'])
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
        apikey.text = args.chain_name

        config_example.write(os.path.join(work_dir, 'node{}/config/config.xml'.format(i)))

        # generate k8s yaml
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