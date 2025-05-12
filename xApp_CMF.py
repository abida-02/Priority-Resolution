#!/usr/bin/env python3

import time
import datetime
import argparse
import signal
import os
import subprocess  # To run shell commands
import csv
from lib.xAppBase import xAppBase


class MyXapp(xAppBase):
    def __init__(self, config, http_server_port, rmr_port):
        super(MyXapp, self).__init__(config, http_server_port, rmr_port)
        self.start_time = time.time()

    def read_recent_decisions(self, file_path, time_threshold):
        """Read recent decisions from a CSV file within the time threshold."""
        recent_decisions = []
        current_time = time.time()

        if not os.path.exists(file_path):
            return recent_decisions

        try:
            with open(file_path, "r") as f:
                current_datetime = datetime.datetime.now()
                print("{} Reading recent control decisions from path: {}, time threshold: {} seconds".format(
                    current_datetime.strftime("%H:%M:%S"), file_path, time_threshold))
                reader = csv.DictReader(f)
                for row in reader:
                    decision_time = float(row["Time"])
                    if current_time - decision_time <= time_threshold:
                        recent_decisions.append({
                            "Time": decision_time,
                            "Datetime": row["Datetime"],
                            "Control_Target_Type": row["Control_Target_Type"],
                            "Control_Target_ID": row["Control_Target_ID"],
                            "Parameter_Name": row["Parameter_Name"],
                            "Parameter_Value": float(row["Parameter_Value"]),
                        })
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

        return recent_decisions

    def detect_and_handle_conflicts(self, recent_decisions_xapp1, recent_decisions_xapp2, block_file_path_xapp1,
                                    block_file_path_xapp2):
        """Detect conflicts and create block files."""
        conflicts = []

        for dec1 in recent_decisions_xapp1:
            for dec2 in recent_decisions_xapp2:
                if (dec1["Control_Target_Type"] == dec2["Control_Target_Type"] and
                        dec1["Control_Target_ID"] == dec2["Control_Target_ID"] and
                        dec1["Parameter_Name"] == dec2["Parameter_Name"] and
                        dec1["Parameter_Value"] != dec2["Parameter_Value"]):
                    conflicts.append((dec1, dec2))

        for conflict in conflicts:
            dec1, dec2 = conflict
            print(
    	        f"Conflict for {dec1['Control_Target_Type']} {dec1['Control_Target_ID']} "
  	        f"for parameter {dec1['Parameter_Name']} and values: {dec1['Parameter_Value']} "
               f"and {dec2['Parameter_Value']}"
)

            # Create block file for non-prioritized xApp #2 once conflict is detected
            if not os.path.exists(block_file_path_xapp2):
                open(block_file_path_xapp2, "w").close()
                print(f"xApp #3: Block file created for xApp #2")

            else:
                print(f"xApp #3: Block file xApp #2 already exists")

    # Mark the function as xApp start function using xAppBase.start_function decorator.
    # It is required to start the internal msg receive loop.
    @xAppBase.start_function
    def start(self):
        # configuration of CD/CR - need to align with xApp #1/#2 logic
        print("Starting CMF xApp - setting up file paths and time threshold")
        xapp1_decision_file_path = os.path.join(os.getcwd(), "xapp_decisions_1.csv")
        xapp2_decision_file_path = os.path.join(os.getcwd(), "xapp_decisions_2.csv")
        xapp1_block_file_path = os.path.join(os.getcwd(), "xapp_1.block")
        xapp2_block_file_path = os.path.join(os.getcwd(), "xapp_2.block")
        time_threshold = 10

        current_datetime = datetime.datetime.now()
        print("{} xApp #1 decision file path: {}, xApp #2 decision file path: {}, xApp #1 block file path: {}, "
              "xApp #2 block file path: {}".format(current_datetime.strftime("%H:%M:%S"),
                                                   xapp1_decision_file_path, xapp1_decision_file_path,
                                                   xapp1_block_file_path, xapp2_block_file_path))

        # detect and resolve conflicts
        while self.running:
            # Read recent decisions from xApp #1 and #2
            print("CMF work in progress - next detection cycle, reading recent control decisions")
            recent_decisions_xapp1 = self.read_recent_decisions(xapp1_decision_file_path, time_threshold)
            recent_decisions_xapp2 = self.read_recent_decisions(xapp2_decision_file_path, time_threshold)

            # Detect and handle conflicts
            print("CMF work in progress - detecting conflicts between recent decisions")
            self.detect_and_handle_conflicts(recent_decisions_xapp1, recent_decisions_xapp2, xapp1_block_file_path,
                                             xapp2_block_file_path)

            time.sleep(1)  # Polling interval


if __name__ == '__main__':
    print("Starting CMF xApp - parsing arguments")
    parser = argparse.ArgumentParser(description='My example xApp')
    parser.add_argument("--config", type=str, default='', help="xApp config file path")
    parser.add_argument("--http_server_port", type=int, default=8093, help="HTTP server listen port")
    parser.add_argument("--rmr_port", type=int, default=4563, help="RMR port")
    parser.add_argument("--ran_func_id", type=int, default=3, help="E2SM RC RAN function ID")

    args = parser.parse_args()
    config = args.config
    ran_func_id = args.ran_func_id

    # Create MyXapp.
    print("Starting CMF xApp - creating myXapp object and setting ran func ID")
    myXapp = MyXapp(config, args.http_server_port, args.rmr_port)
    myXapp.e2sm_rc.set_ran_func_id(ran_func_id)

    # Connect exit signals.
    print("Starting CMF xApp - connecting exit signals")
    signal.signal(signal.SIGQUIT, myXapp.signal_handler)
    signal.signal(signal.SIGTERM, myXapp.signal_handler)
    signal.signal(signal.SIGINT, myXapp.signal_handler)

    # Start xApp.
    print("Starting CMF xApp - calling start() function")
    myXapp.start()

