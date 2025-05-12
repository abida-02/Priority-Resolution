# Priority-Resolution
This method involves only executing one xApp and discarding other existing xApps’s decisions to emphasize the high priority user device.In the test scenario, the CR approach is tailored to the specific roles of the xApps deployed in the system. xApp #1 is responsible for optimizing network performance for high-priority traffic in Slice A, making it the preferred xApp in cases of control conflicts. When both xApp #1 and xApp #2 issue E2 control messages that are active simultaneously and target the same slice, the CD Agent identifies the direct conflict. The CD Agent forwards this information to the CR Agent, which consistently resolves the conflict by rejecting the control decision from xApp #2. As a result, only the control action from xApp #1 is applied to the network, ensuring that the high priority traffic optimization is not affected by competing xApp decisions


## Quick start
#### 1. SC RIC platform

To launch the SC RIC, please run the following command from the `oran-sc-ric` directory:

```bash
docker compose up
```

- To force a new build of the containers, please add a `--build` flag at the end of the previous command.
- To run it in background, please add a `-d` flag at the end of the previous command.
- For more options, check `docker compose up --help`

**Note:** Running this command for the first time may take up to a few minutes, as multiple Docker images have to be downloaded and/or built. A subsequent command execution (i.e., after the environment is ready) starts the RIC in seconds.

#### 2.  5G RAN
We set up an end-to-end 5G network using the **srsRAN_Project gNB** [[docs](https://docs.srsran.com/projects/project/en/latest/),[code](https://github.com/srsran/srsRAN_Project/)] (that is equipped with an E2 agent) and **srsUE** from **srsRAN-4g** project [[docs](https://docs.srsran.com/projects/4g/en/latest/),[code](https://github.com/srsran/srsRAN_4G)]. Please follow the official installation guidelines and remember to compile both projects with **ZeroMQ** support.

We follow this [application note](https://docs.srsran.com/projects/project/en/latest/tutorials/source/flexric/source/index.html), but use the SC RIC instead of [Flexric](https://gitlab.eurecom.fr/mosaic5g/flexric). To this end, we execute gNB and srsUE with the configs provided in the `./e2-agents/srsRAN` directory (gNB config differs only with the IP address of the RIC compared to the config from the tutorial). Note that, we use ZMQ-based RF devices for emulation of the wireless transmission between gNB and UE, therefore the entire RAN setup can be run on a single host machine.

2.1. Start Core Network (here [Open5GS](https://open5gs.org/open5gs/docs/))
```bash
cd  ./srsRAN_Project/docker/
docker compose up --build 5gc
```
2.2. Start gNB:
```bash
cd  ./srsRAN_Project/build/apps/gnb/
sudo ./gnb -c ~/oran-sc-ric/e2-agents/srsRAN/gnb_zmq.yaml
```
The gNB should connect to both the core network and the RIC.  
**Note:** The RIC uses 60s time-to-wait. Therefore, after disconnecting from RIC, an E2 agent (inside gNB) has to wait 60s before trying to connect again. Otherwise, the RIC sends an `E2 SETUP FAILURE` message and gNB is not connected to the RIC.

#### 2.3. COTS UE   https://docs.srsran.com/projects/project/en/latest/tutorials/source/cotsUE/source/index.html
Start   COTS UE:
To connect the COTS UE to the network the following steps must be taken once the phone and network have been correctly configured:

Run the gNB and ensure it is correctly connected to the core

Search for the network from the UE

Select and connect to the network

Verify the attach

[once the started the core will detect the plmn address and register it and an ip address will be assigned]

In the ue terminal start the iperf server by running the following command:
#### iperf3 -s

In another terminal start iperf to generate downlink throughput by running this command with the ipv4 address generated in the core
```bash
sudo iperf3 -c 10.45.0.2 -i 1 -t 5000 -u -b 10M
```
#### Grafana Metrics GUI

To visualize the downlink throughput we can enable the grafana dashboard from srsran project directory  [https://docs.srsran.com/projects/project/en/latest/user_manuals/source/grafana_gui.html]


#### 4. xApp 1 ( app_mode 1)

The xApp in this demo is designed to send rc message to the e2 node. When initially two ue connected to two dufferent slices, the both app will alloc ate resources equally. When third ue joins in slice A, Xapp-1 (app_mode 1) sends rc message to allocate higher resources (prb) to the Slice A and xapp-2 sends rc message to allocate equal resources among the slices. When both xapp is running concurrently it results in an unstable network at the base station resulting in a direct conflict

To start the xapp1, which will prioritize slice A, run the following command
```bash
sudo docker compose exec python_xapp_runner ./xapp_timing_1.py --xapp_id "xApp3" --e2_node_id "gnbd_001_001_00019b_0"  --http_server_port 8090 --app_mode 1 --rmr_port 4560
```


#### 5. xApp 2 (app_mode 2)



```bash
sudo docker compose exec python_xapp_runner ./xapp_timing_1.py --xapp_id "xApp4" --e2_node_id "gnbd_001_001_00019b_0"  --http_server_port 8091 --app_mode 2 ```

```
Enabling gNB console trace (with `t`) allows the monitoring of changes in the downlink (DL) user equipment (UE) data rate.

#### 6. Conflict Detection and Mitigation
In another Terminal run the following command before connecting the third ue. When there is only two ue connected the cmf will execute both apps message. when the third ue connects the cmf will detect the conflcit by reading the decision of each xapps meaaseg. Uplon detection it will create a block file for app_mode 2 which will discard the meassage of xapp 2 and only pass the xapp 1 as priority is assigned to xApp 1.
        
```bash
 sudo docker compose exec python_xapp_runner ./xApp_CMF.py   --rmr_port 4563 --http_server_port 8093
```
The terminal will print this after detecting conflict
```bash
Checking for conflicts upon onboarding xApp xApp1
Logging message from xApp xApp1 at 2025-05-09 11:38:25.396068
Checking for conflicts among 1 recent messages
  
Checking for conflicts upon onboarding xApp xApp2
Logging message from xApp xApp2 at 2025-05-09 11:38:25.434621
Checking for conflicts among 2 recent messages
Conflict detected between messages from  xApp1 and  xApp2
  
Conflict detected. Both  xApp1 and  xApp2 sent conflicting messages.
Initializing Conflict Mitigation Module
Buffering message from  xApp2 for later execution.
Executing buffered message from xApp xApp2 after delay.
Initializing Conflict Mitigation Module

```
#### Result Evaluation 
In the runs with CM enabled, when the third UE connects to the network, the DL throughput changes for each UE as the network adapts to the new PRB allocations, but then remains stable. In contrast to the runs without CM, no significant metric fluctuations are observed. This is due to the CM measure causing control decisions from xApp #1 to take precedence over decisions from xApp #2, allowing for the network to reach a stable state

