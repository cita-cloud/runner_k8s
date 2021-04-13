# runner_k8s

本工具帮助用户方便的在`k8s`环境中启动一条`CITA-Cloud`链。本工具会为链的每一个节点生成必须的配置文件，以及用于部署到`k8s`的`yaml`文件。

## 单集群
链的所有节点都在同一个`k8s`集群中。
### 依赖

* python 3
* docker

安装依赖包:

```
pip install -r requirements.txt
```

### 使用方法

```
$ ./create_k8s_config.py local_cluster -h
usage: create_k8s_config.py local_cluster [-h] [--block_delay_number BLOCK_DELAY_NUMBER] [--chain_name CHAIN_NAME]
                                          [--peers_count PEERS_COUNT] [--kms_password KMS_PASSWORD]
                                          [--state_db_user STATE_DB_USER] [--state_db_password STATE_DB_PASSWORD]
                                          [--service_config SERVICE_CONFIG] [--data_dir DATA_DIR] [--node_port NODE_PORT]
                                          [--need_monitor NEED_MONITOR] [--nfs_server NFS_SERVER] [--nfs_path NFS_PATH]

optional arguments:
  -h, --help            show this help message and exit
  --block_delay_number BLOCK_DELAY_NUMBER
                        The block delay number of chain.
  --chain_name CHAIN_NAME
                        The name of chain.
  --peers_count PEERS_COUNT
                        Count of peers.
  --kms_password KMS_PASSWORD
                        Password of kms.
  --state_db_user STATE_DB_USER
                        User of state db.
  --state_db_password STATE_DB_PASSWORD
                        Password of state db.
  --service_config SERVICE_CONFIG
                        Config file about service information.
  --data_dir DATA_DIR   Root data dir where store data of each node.
  --node_port NODE_PORT
                        The node port of rpc.
  --need_monitor NEED_MONITOR
                        Is need monitor
  --nfs_server NFS_SERVER
                        Address of nfs server.
  --nfs_path NFS_PATH   Path of nfs .

```

### 生成配置

`cita-cloud`分为六个微服务：`network`, `consensus`, `executor`, `storage`, `controller`, `kms`。

每个微服务都可能有多个不同的实现，`service-config.toml`用来配置每个微服务分别选择哪些实现，以及相应的启动命令。

目前微服务的实现有：

1. `network`。目前只有`network_p2p`这一个实现，选择该实现，需要将`is_need_network_key`设置为`true`。
2. `consensus`。目前有`consensus_raft`一个实现。
3. `executor`。目前有`executor_chaincode`和`executor_chaincode_ext`两个实现，其中`executor_chaincode_ext`是不开源的。
4. `storage`。目前有`storage_sqlite`和`storage_tikv`两个实现。如果选择使用`storage_tikv`，需要先按照[文档](https://tikv.org/docs/4.0/tasks/try/tikv-operator/)安装运行`tikv`。
5. `controller`。目前只有`controller_poc`这一个实现。
6. `kms`。目前有`kms_eth`和`kms_sm`两个实现，分别兼容以太坊和国密。

注意：六个微服务缺一不可；每个微服务只能选择一个实现，不能多选。

运行命令生成相应的文件。`kms`的密码，`state db`的用户名和密码是必选参数，其他参数使用默认值。

```shell
$ ./create_k8s_config.py local_cluster --kms_password 123456 --peers_count 3 --state_db_user citacloud --state_db_password 123456
$ ls
cita-cloud  test-chain.yaml
```

生成的`cita-cloud`目录结构如下：
```
$ tree cita-cloud
cita-cloud
└── test-chain
    ├── node0
    ├── node1
    ├── node2
```

最外层是`cita-cloud`；第二层是链的名称，跟`chain_name`参数保持一致；最里面是各个节点的文件夹。

`node0`，`node1`, `node2`是三个节点文件夹，里面有相应节点的配置文件。

`test-chain.yaml`用于将链部署到`k8s`，里面声明了必需的`secret`/`pod`/`service`，文件名跟`chain_name`参数保持一致。


### NFS
默认的文件挂载方式是`hostPath`，这个只能用于测试。

正式生产环境请使用`nfs`,通过`nfs_server`和`nfs_path`两个参数传递`NFS`的`ip`和路径。

如果没有设置`nfs`相关的参数，则默认使用`hostPath`，如果设置了`nfs`相关的参数，则优先使用`nfs`。

### Node Port

为了方便客户端使用，需要暴露到集群外的端口都设置了固定的端口号。同时为了防止在一个集群中部署多条链时引起端口冲突，通过`node_port`参数传递起始端口号，各个需要暴露的端口号依如下次序递增：

1. `RPC`端口为`node_port`参数的值。
2. 如果`need_monitor`设置为`true`，每个节点会有两个`monitor`端口，分别是`process`和`exporter`。它们的端口号分别为`node_port + 1 + 5 * i`和`node_port + 1 + 5 * i + 1`。
3. 如果`executor`为`chaincode`。每个节点会有：一个`chaincode`端口，端口号是`node_port + 1 + 5 * i + 2`；一个`eventhub`端口，端口号是`node_port + 1 + 5 * i + 3`；一个`call`端口，端口号是`node_port + 1 + 5 * i + 4`；

以`node_port`参数默认值30004，三个节点为例：

```
test-chain-node-port     50004:30004/TCP  // RPC端口

monitor-test-chain-0     9256:30005/TCP,9349:30006/TCP    // node0的两个监控端口
monitor-test-chain-1     9256:30010/TCP,9349:30011/TCP    // node1的两个监控端口
monitor-test-chain-2     9256:30015/TCP,9349:30016/TCP    // node1的两个监控端口

chaincode-test-chain-0   7052:30007/TCP,7053:30008/TCP,50002:30009/TCP   // node0的chaincode相关的三个端口
chaincode-test-chain-1   7052:30012/TCP,7053:30013/TCP,50002:30014/TCP   // node1的chaincode相关的三个端口
chaincode-test-chain-2   7052:30017/TCP,7053:30018/TCP,50002:30019/TCP   // node2的chaincode相关的三个端口
```

注意：无论功能是否打开，相关的端口号都会保留。例如，即使没有打开监控功能，chaincode的端口号依然跟上述例子相同。

### 部署

这里演示的是在单机的`minikube`环境中部署，确保`minikube`已经在本机安装并正常运行。

```shell
$ minikube ssh
docker@minikube:~$ mkdir cita-cloud-datadir
docker@minikube:~$ exit
$ scp -i ~/.minikube/machines/minikube/id_rsa -r cita-cloud docker@`minikube ip`:~/cita-cloud-datadir/
$ kubectl apply -f test-chain.yaml
secret/kms-secret created
service/test-chain-node-port created
secret/node0-network-secret created
service/test-chain-0 created
pod/test-chain-0 created
secret/node1-network-secret created
service/test-chain-1 created
pod/test-chain-1 created
secret/node2-network-secret created
service/test-chain-2 created
pod/test-chain-2 created
```

查看运行情况：

```shell
$ minikube ssh
docker@minikube:~$ tail -10f cita-cloud-datadir/cita-cloud/test-chain/node0/logs/controller-service.log  
2020-08-27T07:42:43.280172163+00:00 INFO controller::chain - 1 blocks finalized
2020-08-27T07:42:43.282871996+00:00 INFO controller::chain - executed block 1397 hash: 0x 16469..e061
2020-08-27T07:42:43.354375501+00:00 INFO controller::pool - before update len of pool 0, will update 0 tx
2020-08-27T07:42:43.354447445+00:00 INFO controller::pool - after update len of pool 0
2020-08-27T07:42:43.354467947+00:00 INFO controller::pool - low_bound before update: 0
2020-08-27T07:42:43.354484999+00:00 INFO controller::pool - low_bound after update: 0
2020-08-27T07:42:43.385062636+00:00 INFO controller::controller - get block from network
2020-08-27T07:42:43.385154627+00:00 INFO controller::controller - add block
2020-08-27T07:42:43.386148650+00:00 INFO controller::chain - add block 0x 11cf7..cad9
2020-08-27T07:42:46.319058783+00:00 INFO controller - reconfigure consensus!
```

停止

```
$ kubectl delete -f test-chain.yaml 
secret "kms-secret" deleted
service "test-chain-node-port" deleted
secret "node0-network-secret" deleted
service "test-chain-0" deleted
pod "test-chain-0" deleted
secret "node1-network-secret" deleted
service "test-chain-1" deleted
pod "test-chain-1" deleted
secret "node2-network-secret" deleted
service "test-chain-2" deleted
pod "test-chain-2" deleted
```


## 多集群
链的节点分布在多个`k8s`集群中。此部分内容跟单集群部分重复的地方将不再赘述，仅描述差异的内容。
### 依赖

* python 3
* [syncthing](https://syncthing.net)
* [kms_sm](https://github.com/cita-cloud/kms_sm) 或者 [kms_eth](https://github.com/cita-cloud/kms_eth)

安装依赖包:

```
pip install -r requirements.txt
```

### 使用方法
```
$ ./create_k8s_config.py local_cluster -h
usage: create_k8s_config.py multi_cluster [-h] [--block_delay_number BLOCK_DELAY_NUMBER] [--chain_name CHAIN_NAME]
                                          [--service_config SERVICE_CONFIG] [--need_monitor NEED_MONITOR]
                                          [--timestamp TIMESTAMP] [--super_admin SUPER_ADMIN] [--authorities AUTHORITIES]   
                                          [--nodes NODES] [--lbs_tokens LBS_TOKENS] [--sync_device_ids SYNC_DEVICE_IDS]     
                                          [--kms_passwords KMS_PASSWORDS] [--node_ports NODE_PORTS]
                                          [--nfs_servers NFS_SERVERS] [--nfs_paths NFS_PATHS] [--data_dir DATA_DIR]
                                          [--state_db_user STATE_DB_USER] [--state_db_password STATE_DB_PASSWORD]

optional arguments:
  -h, --help            show this help message and exit
  --block_delay_number BLOCK_DELAY_NUMBER
                        The block delay number of chain.
  --chain_name CHAIN_NAME
                        The name of chain.
  --service_config SERVICE_CONFIG
                        Config file about service information.
  --need_monitor NEED_MONITOR
                        Is need monitor
  --timestamp TIMESTAMP
                        Timestamp of genesis block.
  --super_admin SUPER_ADMIN
                        Address of super admin.
  --authorities AUTHORITIES
                        Authorities (addresses) list.
  --nodes NODES         Node network ip list.
  --lbs_tokens LBS_TOKENS
                        The token list of LBS.
  --sync_device_ids SYNC_DEVICE_IDS
                        Device id list of syncthings.
  --kms_passwords KMS_PASSWORDS
                        Password list of kms.
  --node_ports NODE_PORTS
                        The list of start port of Nodeport.
  --nfs_servers NFS_SERVERS
                        The list of nfs servers.
  --nfs_paths NFS_PATHS
                        The list of nfs paths.
  --data_dir DATA_DIR   Root data dir where store data of each node.
  --state_db_user STATE_DB_USER
                        User of state db.
  --state_db_password STATE_DB_PASSWORD
                        Password of state db.
```

### 生成配置

多集群模式下只支持`nfs`存储，且要求集群提供`loadBalancer`服务，以便多个集群之间可以通过外部`IP`或域名相互访问。

#### 准备工作

##### 生成`super admin`账户。

```
$ echo "password" > key_file
$ ls
create_account.py  key_file  kms  kms.db  kms-log4rs.yaml  logs
$ ./create_account.py
kms create output: key_id:1,address:0x88b3fd84e3b10ac04cd04def0876cb513452c74e
$ ls
0x88b3fd84e3b10ac04cd04def0876cb513452c74e  create_account.py  kms  kms-log4rs.yaml  logs
$ ls 0x88b3fd84e3b10ac04cd04def0876cb513452c74e
key_file  key_id  kms.db  node_address
```

`0x88b3fd84e3b10ac04cd04def0876cb513452c74e`为账户地址。

`key_id`和`kms.db`分别保存了账户的`id`和私钥，后续需要使用，所以先归档到以账户地址命名的文件夹中。

使用同样的方法，按照规划的节点数量，为每个节点都生成一个账户地址。
```
kms create output: key_id:1,address:0xbdfa0bbd30e5219d7778c461e49b600fdfb703bb
kms create output: key_id:1,address:0xdff342dadae5abcb4ca9f899c2168ab69f967c85
kms create output: key_id:1,address:0x914743835c855baf2f59015179f89f4f7f59e3ff
```

创建这三个节点账号时的密码，也要作为创建配置时的参数。

假设密码分别为：`password0`,`password1`,`password2`。

##### 创建`syncthing`的`device id`。

```
$ ls
create_syncthing_config.py
$ ./create_syncthing_config.py
device_id: 536EVEY-MZPLRMI-XWOOAXV-OWMHHNC-ZSE25NQ-Z22TZIS-YKPTCKJ-ESBUUQW
$ ls
536EVEY-MZPLRMI-XWOOAXV-OWMHHNC-ZSE25NQ-Z22TZIS-YKPTCKJ-ESBUUQW  create_syncthing_config.py
$ ls 536EVEY-MZPLRMI-XWOOAXV-OWMHHNC-ZSE25NQ-Z22TZIS-YKPTCKJ-ESBUUQW
cert.pem  key.pem
```

`536EVEY-MZPLRMI-XWOOAXV-OWMHHNC-ZSE25NQ-Z22TZIS-YKPTCKJ-ESBUUQW`为生成的`device id`。

`cert.pem`和`key.pem`为对应的证书文件，后续需要使用，所以先归档到以`device id`命名的文件夹中。

使用同样的方法，按照规划的节点数量，为每个节点都生成一个`device id`。

```
device_id: NVSFY4A-Z22XP3J-WHA5GPL-AGFCVVA-IWECW3E-GE34T2O-3MUXT63-LTE6YQP
device_id: EROQJHV-QCEVWQB-F5ZD72M-ZEIRKGP-XLGJWBL-JQZ44AO-UO7NSWQ-7TK3HQJ
device_id: MWVAAOD-YGTHWBA-WG2BMRY-GCB5O5V-JR5JYRU-WL5YYEW-5CURT7W-4ZUVEQY
```

##### 创建集群`loadbanlancer`

此处操作请咨询当前使用的云服务商。

以阿里云为例，创建之后会得到一个集群对外的`ip`和一个形如`lb-hddhfjg****`的`LoadBalancerId`。

这里假设有三个集群，对外`ip`分别为：`cluster0_ip`,`cluster1_ip`,`cluster2_ip`;`LoadBalancerId`分别为：`lb-hddhfjg1234`,`lb-hddhfjg2234`,`lb-hddhfjg3234`。

##### 端口分配

每个节点有8个端口需要暴露到集群之外：

1. 网络 40000
2. syncthing 22000
3. rpc 50004
4. monitor_process 9256
5. monitor_exporter 9349
6. executor_call 50002
7. executor_chaincode 7052
8. executor_eventhub 7053
   
所以需要预留连续的8个端口，然后将起始端口作为创建配置时的参数。

比如，预留端口为30000~30007，则要使用的参数为30000。

##### 安装`NFS`服务

节点的存储使用集群内的`NFS`服务。

需要事先在集群内安装`NFS`服务。记录服务的`ip`和路径，作为创建配置时的参数。

这里假设有三个集群，`nfs_server`的`ip`分别为：`nfs0_ip`,`nfs1_ip`,`nfs2_ip`;路径分别为：`/data/nfs0`,`/data/nfs1`,`/data/nfs2`。

#### 生成配置文件

使用前述准备工作中准备好的信息生成配置文件。

注意：三个集群的各项信息，其顺序一定要保持一致。

```
$ ./create_k8s_config.py multi_cluster --authorities 0xbdfa0bbd30e5219d7778c461e49b600fdfb703bb,0xdff342dadae5abcb4ca9f899c2168ab69f967c85,0x914743835c855baf2f59015179f89f4f7f59e3ff --nodes cluster0_ip,cluster1_ip,cluster2_ip --lbs_tokens lb-hddhfjg1234,lb-hddhfjg2234,lb-hddhfjg3234 --sync_device_ids NVSFY4A-Z22XP3J-WHA5GPL-AGFCVVA-IWECW3E-GE34T2O-3MUXT63-LTE6YQP,EROQJHV-QCEVWQB-F5ZD72M-ZEIRKGP-XLGJWBL-JQZ44AO-UO7NSWQ-7TK3HQJ,MWVAAOD-YGTHWBA-WG2BMRY-GCB5O5V-JR5JYRU-WL5YYEW-5CURT7W-4ZUVEQY --kms_passwords password0,password1,password2 --node_ports 30000,30000,30000 --nfs_servers nfs0_ip,nfs1_ip,nfs2_ip --nfs_paths /data/nfs0,/data/nfs1,/data/nfs2 --super_admin 0x88b3fd84e3b10ac04cd04def0876cb513452c74e
$ ls
cita-cloud  test-chain-0.yaml  test-chain-1.yaml  test-chain-2.yaml
```

生成的`cita-cloud`目录结构如下：
```
$ tree cita-cloud
cita-cloud
└── test-chain
    ├── node0
    ├── node1
    ├── node2
```

三个`yaml`文件分别是用于部署对应节点到`k8s`集群的配置文件。

#### 后续处理

上面生成的配置文件并不完整，还需要将准备阶段归档的文件拷贝进去补充完整。

节点0对应的账户为`0xbdfa0bbd30e5219d7778c461e49b600fdfb703bb`，因此需要将创建该账号时归档的`node_address`,`key_id`和`kms.db`三个文件拷贝到`cita-cloud/test-chain/node0/`下。

节点0对应的`device id`为`NVSFY4A-Z22XP3J-WHA5GPL-AGFCVVA-IWECW3E-GE34T2O-3MUXT63-LTE6YQP`。因此需要将创建该`device id`时归档的`cert.pem`和`key.pem`两个文件拷贝到`cita-cloud/test-chain/node0/config/`下。

其他两个节点采用同样的操作进行处理。

### 部署

将三个节点配置文件夹分别下发到对应集群的`NFS`服务器上，但是注意要保持三层目录结构不变。

在三个`k8s`集群中，分别应用对应节点的`yaml`文件，启动节点。