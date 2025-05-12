#!/usr/bin/env python3

import time
import datetime
import argparse
import signal
import logging
import requests
import math
import csv
import os
from lib.xAppBase import xAppBase
from central_controller import CentralController

class MyXapp(xAppBase):
    def __init__(self, config, http_server_port, rmr_port, controller, xapp_id, flask_server_url, app_mode):
        super(MyXapp, self).__init__(config, http_server_port, rmr_port)
        self.controller = controller
        self.xapp_id = xapp_id
        self.start_time = time.time()
        self.processed_messages = 0
        self.latencies = []
        self.flask_server_url = flask_server_url
        self.latestUeCount = 0
        self.app_mode = app_mode
        
        
       # Latency Log Header

        self.uesSliceA = [
            {'id': 0, 'sst': 1, 'sd': 16777210},
            {'id': 2, 'sst': 1, 'sd': 16777210}
        ]
        self.uesSliceB = [
            {'id': 1, 'sst': 1, 'sd': 16777215}
        ]
        self.slices = [
            {'sd': 16777210, 'sst': 1, 'name': 'A'},
            {'sd': 16777215, 'sst': 1, 'name': 'B'},
        ]

    def my_subscription_callback(self, e2_agent_id, subscription_id, indication_hdr, indication_msg, kpm_report_style, ue_id):
        indication_hdr = self.e2sm_kpm.extract_hdr_info(indication_hdr)
        meas_data = self.e2sm_kpm.extract_meas_data(indication_msg)
        start_time = time.time()  # Record start time

        print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: Data Monitoring:")
        print("  E2SM_KPM RIC Indication Content:")
        print("  -ColletStartTime: ", indication_hdr['colletStartTime'])
        print("  -Measurements Data:")

        # Process UE measurement data
        for ue_id, ue_meas_data in meas_data["ueMeasData"].items():
            print("  --UE_id: {}".format(ue_id))
            granulPeriod = ue_meas_data.get("granulPeriod", None)
            if granulPeriod is not None:
                print("  ---granulPeriod: {}".format(granulPeriod))

            for metric_name, values in ue_meas_data["measData"].items():
                print("  ---Metric: {}, Value: {:.1f} [MB]".format(metric_name, sum(values) / 8 / 1000))

        # Log the latency to the CSV file
        latency = time.time() - start_time  # Time difference in seconds

        # Prepare data for CSV
        log_file_path = 'xapp_timing_1.csv'  # Path to the latency log file
        csv_headers = ['Time', 'UE_id', 'Metric', 'Value', 'latency']
        
        # Open the CSV file in append mode and write data
        with open(log_file_path, 'a', newline='') as csv_file:
            csv_writer = csv.writer(csv_file)

            # Write headers only once (if file is empty)
            if csv_file.tell() == 0:
                csv_writer.writerow(csv_headers)

            # Process UE-level measurement data
            for ue_id, ue_meas_data in meas_data["ueMeasData"].items():
                print("--UE_id: {}".format(ue_id))
                #granulPeriod = ue_meas_data.get("granulPeriod", None)
                #if granulPeriod is not None:
                  #  print("---granulPeriod: {}".format(granulPeriod))

                # Log each metric and value for the UE in the CSV
                for metric_name, value in ue_meas_data["measData"].items():
                    print("---Metric: {}, Value: {}".format(metric_name, value))
                    # Append row to the CSV file
                    csv_writer.writerow([
                        indication_hdr['colletStartTime'],
                        ue_id,
                        metric_name,
                        value[0] / 8 / 1000 if isinstance(value, list) else value,  # Convert bytes to MB
                        latency  # Log the latency for each trigger
                    ])

        print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: Metrics logged to {log_file_path}")

        # Count UEs and update latest UE count held in xApp logic
        ue_meas_data_items = meas_data["ueMeasData"].items()
        ueCount = len(ue_meas_data_items)
        self.updateLatestUeCount(ueCount)

    def updateLatestUeCount(self, latestUeCount):
        self.latestUeCount = latestUeCount

    def getLatestUeCount(self):
        # it shall return 2 or 3 based on current total number of UEs in all slices
        return self.latestUeCount

    def setup_subscription(self, e2_node_id):
        print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: Setting up subscription for xApp...")
        metric_names = [ 'DRB.UEThpDl']
        kpm_report_style = 5  # previously 4

        # this is code for configuration of KPM report style 4 from kpm_mon_xapp.py's start method
        report_period = 1000
        granul_period = 1000

        # use always the same subscription callback, but bind kpm_report_style parameter
        subscription_callback = lambda agent, sub, hdr, msg: self.my_subscription_callback(agent, sub, hdr, msg,
                                                                                           kpm_report_style, None)

        # currently only dummy condition that is always satisfied, useful to get IDs of all connected UEs
        # example matching UE condition: ul-rSRP < 1000
        matchingUeConds = [{'testCondInfo': {'testType': ('ul-rSRP', 'true'), 'testExpr': 'lessthan',
                                             'testValue': ('valueInt', 1000)}}]

        print("Subscribe to E2 node ID: {}, RAN func: e2sm_kpm, Report Style: {}, metrics: {}".format(e2_node_id,
                                                                                                      kpm_report_style,
                                                                                                      metric_names))
        self.e2sm_kpm.subscribe_report_service_style_4(e2_node_id, report_period, matchingUeConds, metric_names,
                                                       granul_period, subscription_callback)

    def process(self, totalSliceCount, totalPrbCount, totalUeCount, ueCountSliceA):
        # Check if xApp is blocked from performing control decisions due to CM measures
        print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: Starting processing of PRB allocations.")
        block_file_name = 'xapp_{}.block'.format(self.app_mode)
        block_file_path = os.path.join(os.getcwd(), block_file_name)
        if os.path.exists(block_file_path):
            print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: Block file detected. Ceasing control decisions.")
            return

        print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: Block file not detected. Proceeding to process PRB allocations.")
        if self.app_mode == 1:
            prbAllocations_xApp = self.process_xApp_1(totalSliceCount=totalSliceCount,
                                                      totalPrbCount=totalPrbCount,
                                                      ueCountSliceA=ueCountSliceA,
                                                      totalUeCount=totalUeCount)
        elif self.app_mode == 2:
            prbAllocations_xApp = self.process_xApp_2(totalSliceCount=totalSliceCount,
                                                      totalPrbCount=totalPrbCount)

        print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: PRB Allocations: {prbAllocations_xApp}")
        # Continue with PRB control based on calculated allocations
        # (The rest of the process method code remains unchanged)


        # Continue with PRB control based on calculated allocations
        # 1) for Slice A
        prbAllocationSliceA = prbAllocations_xApp[0]
        ueAllocationsSliceA = self.computeAllocationsForSlice(prbAllocation=prbAllocationSliceA,
                                                              ueCountSlice=ueCountSliceA)
        print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: {prbAllocationSliceA} PRBs allocated to Slice A, split among UEs: {ueAllocationsSliceA}")
        for i, prbAllocationForUe in enumerate(ueAllocationsSliceA):
            ue = self.uesSliceA[i]
            ue_id = ue['id']
            sst = ue['sst']
            sd = ue['sd']
            current_time = time.time()
            current_datetime = datetime.datetime.now()
            print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: Sending RIC Control Request to E2 node ID: {e2_node_id} slice: {sd} for UE ID: {ue_id}, PRB: {prbAllocationForUe}")
            # print("{} [{}] Send RIC Control Request to E2 node ID: {} slice: {} for UE ID: {}, PRB: {}".format(
            #    current_datetime.strftime("%H:%M:%S"), self.xapp_id, e2_node_id, sd, ue_id, prbAllocationForUe))

            # Log the message with the CentralController
            self.controller.log_message(self.xapp_id, e2_node_id, ue_id, prbAllocationForUe, prbAllocationForUe,
                                        current_time)
            # Execute the RAN control
            self.e2sm_rc.control_slice_level_prb_quota(e2_node_id, ue_id, min_prb_ratio=prbAllocationForUe,
                                                       max_prb_ratio=prbAllocationForUe, dedicated_prb_ratio=100,
                                                       ack_request=1, sst=sst, sd=sd)
            print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: Sent RIC Control Request to E2 node ID: {e2_node_id} slice: {sd} for UE ID: {ue_id}, PRB: {prbAllocationForUe}")
            self.log_control_decision(current_time, current_datetime, "USER", ue_id, "PRB_ALLOCATION", prbAllocationForUe)

        # 2) for Slice B
        prbAllocationSliceB = prbAllocations_xApp[1]
        ueCountSliceB = totalUeCount - ueCountSliceA
        ueAllocationsSliceB = self.computeAllocationsForSlice(prbAllocation=prbAllocationSliceB,
                                                              ueCountSlice=ueCountSliceB)
        print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: {prbAllocationSliceB} PRBs allocated to Slice B, split among UEs: {ueAllocationsSliceB}")
        for i, prbAllocationForUe in enumerate(ueAllocationsSliceB):
            ue = self.uesSliceB[i]
            ue_id = ue['id']
            sst = ue['sst']
            sd = ue['sd']
            current_time = time.time()
            current_datetime = datetime.datetime.now()
            print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: Sending RIC Control Request to E2 node ID: {e2_node_id} slice: {sd} for UE ID: {ue_id}, PRB: {prbAllocationForUe}")
            #print("{} [{}] Send RIC Control Request to E2 node ID: {} slice: {} for UE ID: {}, PRB: {}".format(
            #    current_datetime.strftime("%H:%M:%S"), self.xapp_id, e2_node_id, sd, ue_id, prbAllocationForUe))

            # Log the message with the CentralController
            self.controller.log_message(self.xapp_id, e2_node_id, ue_id, prbAllocationForUe, prbAllocationForUe,
                                        current_time)
            # Execute the RAN control
            self.e2sm_rc.control_slice_level_prb_quota(e2_node_id, ue_id, min_prb_ratio=prbAllocationForUe,
                                                       max_prb_ratio=prbAllocationForUe,
                                                       dedicated_prb_ratio=100,
                                                       ack_request=1, sst=sst, sd=sd)
            print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: Sent RIC Control Request to E2 node ID: {e2_node_id} slice: {sd} for UE ID: {ue_id}, PRB: {prbAllocationForUe}")
            self.log_control_decision(current_time, current_datetime, "USER", ue_id, "PRB_ALLOCATION", prbAllocationForUe)

    @xAppBase.start_function
    def start(self, e2_node_id, kpm_report_style, ue_ids, metric_names):
        report_period = 1000
        granul_period = 1000
        self.setup_subscription(e2_node_id)
        subscription_callback = lambda agent, sub, hdr, msg: self.my_subscription_callback(agent, sub, hdr, msg,
                                                                                           kpm_report_style, None)

        # Dummy condition that is always satisfied
        matchingUeConds = [{'testCondInfo': {'testType': ('ul-rSRP', 'true'), 'testExpr': 'lessthan',
                                             'testValue': ('valueInt', 1000)}}]

        print("Subscribe to E2 node ID: {}, RAN func: e2sm_kpm, Report Style: {}, metrics: {}".format(e2_node_id,
                                                                                                      kpm_report_style,
                                                                                                      metric_names))
        self.e2sm_kpm.subscribe_report_service_style_4(e2_node_id, report_period, matchingUeConds, metric_names,
                                                       granul_period, subscription_callback)

        while self.running:
            totalSliceCount = 2  # always 2 slices (A and B)
            totalPrbCount = 51  # always 51 PRBs for entire RAN
            totalUeCount = self.getLatestUeCount()  # get from network observation
            ueCountSliceA = totalUeCount - 1  # assumed 1 UEs in slices other than A (i.e., in slice B)

            if totalUeCount == 0:
                print(f"[{datetime.datetime.now()}] xApp #{self.app_mode}: No UEs detected based on E2 indication message, waiting...")
                time.sleep(1)
                continue

            start_processing_time = time.time()
            if app_mode == 1:
                execution_trigger = 0
            if app_mode == 2:
                execution_trigger = 5

            execution_timer = math.floor(start_processing_time % 10)

            print(f"[{start_processing_time}] xApp #{self.app_mode}: execution timer is: {execution_timer} with execution trigger: {execution_trigger}")

            if (execution_timer == execution_trigger):
                self.process(totalSliceCount, totalPrbCount, totalUeCount, ueCountSliceA)

                # Record metrics
                self.processed_messages += 1
                end_processing_time = time.time()
                latency = end_processing_time - start_processing_time
                self.latencies.append(latency)

                # Print metrics periodically
                if self.processed_messages % 10 == 0:
                    self.print_metrics()

            time.sleep(1)

    def print_metrics(self):
        elapsed_time = time.time() - self.start_time
        throughput = self.processed_messages / elapsed_time
        average_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        metrics = (f"Throughput: {throughput:.2f} messages/sec\n"
                   f"Average Latency: {average_latency:.4f} seconds")
        print(metrics)
        logging.info(metrics)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='My example xApp')
    parser.add_argument("--config", type=str, default='', help="xApp config file path")
    parser.add_argument("--http_server_port", type=int, default=8090, help="HTTP server listen port")
    parser.add_argument("--rmr_port", type=int, default=4560, help="RMR port")
    parser.add_argument("--e2_node_id", type=str, default='gnbd_001_001_00019b_0', help="E2 Node ID")
    parser.add_argument("--ran_func_id", type=int, default=2, help="E2SM KPM RAN function ID")  # default 3
    parser.add_argument("--xapp_id", type=str, required=True, help="Unique ID for the xApp instance")
    parser.add_argument("--flask_server_url", type=str, default='http://localhost:5000',
                        help="URL of the Flask dashboard server")
    parser.add_argument("--kpm_report_style", type=int, default=4, help="KPM Report Style ID")
    parser.add_argument("--ue_ids", type=str, default='0', help="UE ID")
    parser.add_argument("--metrics", type=str, default='DRB.RlcSduTransmittedVolumeDL',
                        help="Metrics name as comma-separated string")
    parser.add_argument("--app_mode", type=int, default=1, help="xApp mode; 1 or 2")

    args = parser.parse_args()
    config = args.config
    e2_node_id = args.e2_node_id
    ran_func_id = args.ran_func_id
    xapp_id = args.xapp_id
    flask_server_url = args.flask_server_url
    ue_ids = list(map(int, args.ue_ids.split(",")))  # Note: the UE id has to exist at E2 node!
    kpm_report_style = args.kpm_report_style
    metrics = args.metrics.split(",")
    app_mode = args.app_mode
    # Create CentralController
    controller = CentralController()

    # Create MyXapp with controller and Flask server URL
    myXapp = MyXapp(config, args.http_server_port, args.rmr_port, controller, xapp_id, flask_server_url, app_mode)
    # myXapp.e2sm_rc.set_ran_func_id(ran_func_id)
    myXapp.e2sm_kpm.set_ran_func_id(ran_func_id)

    signal.signal(signal.SIGQUIT, myXapp.signal_handler)
    signal.signal(signal.SIGTERM, myXapp.signal_handler)
    signal.signal(signal.SIGINT, myXapp.signal_handler)

    myXapp.start(e2_node_id, kpm_report_style, ue_ids, metrics)

