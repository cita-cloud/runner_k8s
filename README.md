# runner_k8s

本工具帮助用户方便的在`k8s`环境中启动一条`cita-cloud`链。本工具会为链的每一个节点生成必须的配置文件，以及用于部署到`k8s`的`yaml`文件。

### 依赖

* python 3
* docker

### 使用方法

```
$ ./create_k8s_config.py local_cluster -h                                   
usage: create_k8s_config.py local_cluster [-h] [--block_delay_number BLOCK_DELAY_NUMBER] [--chain_name CHAIN_NAME]
                                          [--peers_count PEERS_COUNT] [--kms_password KMS_PASSWORD] [--state_db_user STATE_DB_USER]
                                          [--state_db_password STATE_DB_PASSWORD] [--service_config SERVICE_CONFIG]
                                          [--data_dir DATA_DIR]

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
```

### 生成配置

`cita-cloud`分为六个微服务：`network`, `consensus`, `executor`, `storage`, `controller`, `kms`。

每个微服务都可能有多个不同的实现，`service-config.toml`用来配置每个微服务分别选择哪些实现，已经相应的启动命令。

目前有的微服务实现有：

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
node0  node1 node2  test-chain.yaml
```

`node0`，`node1`, `node2`是三个节点文件夹，里面有相应节点的配置文件。`test-chain.yaml`用于将链部署到`k8s`，里面声明了必需的`secret`/`pod`/`service`，文件名跟`chain_name`参数保持一致。

### 部署

这里演示的是在单机的`minikube`环境中部署，确保`minikube`已经在本机安装并正常运行。

```shell
$ minikube ssh
docker@minikube:~$ mkdir cita-cloud-datadir
docker@minikube:~$ exit
$ scp -i ~/.minikube/machines/minikube/id_rsa -r ./node* docker@`minikube ip`:~/cita-cloud-datadir/
$ kubectl apply -f test-chain.yaml
secret/kms-secret created
service/test-chain-loadbalancer created
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
docker@minikube:~$ tail -10f cita-cloud-datadir/node0/logs/controller-service.log  
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

映射`RPC`端口，然后可以进行一些测试。

```
$ kubectl port-forward svc/test-chain-loadbalancer 50004:50004
Forwarding from 127.0.0.1:50004 -> 50004
Forwarding from [::1]:50004 -> 50004
```

映射`chaincode`端口
```
$ kubectl port-forward pod/test-chain-0 7052:7052
Forwarding from 127.0.0.1:7052 -> 7052
Forwarding from [::1]:7052 -> 7052
```

停止

```
$ kubectl delete -f test-chain.yaml 
secret "kms-secret" deleted
service "test-chain-loadbalancer" deleted
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

