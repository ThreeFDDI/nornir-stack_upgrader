#!/usr/local/bin/python3
'''
This script is used to upgrade software on Cisco Catalyst 3750 and 3650 switch stacks.
'''

import threading
import socketserver
import os, sys, time, socket
from getpass import getpass
from nornir import InitNornir
from nornir.core.filter import F
from nornir.plugins.functions.text import print_result
from nornir.plugins.tasks.networking import netmiko_send_config
from nornir.plugins.tasks.networking import netmiko_send_command
from nornir.plugins.tasks.networking import netmiko_file_transfer
from http.server import SimpleHTTPRequestHandler
from pprint import pprint as pp


# http server for file transfer
class ThreadedHTTPServer(object):
    handler = SimpleHTTPRequestHandler
    def __init__(self, host, port):
        self.server = socketserver.TCPServer((host, port), self.handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True

    def start(self):
        self.server_thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


# print formatting function
def c_print(printme):
    # Print centered text with newline before and after
    print(f"\n" + printme.center(80, ' ') + "\n")


# continue banner
def proceed():
    # print banner to proceed
    c_print('********** PROCEED? **********')
    # capture user input
    confirm = input(" "*36 + '(y/n) ')
    # quit script if not confirmed
    if confirm.lower() != 'y':
        c_print("******* EXITING SCRIPT *******")
        print('~'*80)    
        exit()
    else:
        c_print("********* PROCEEDING *********")


# set device credentials
def kickoff(norn, username=None, password=None):
    # print banner
    print()
    print('~'*80)
    c_print('This script will upgrade software on Cisco Catalyst switch stacks')
    #c_print(f"*** {task.host}: dot1x configuration applied ***")
    c_print('Checking inventory for credentials')
    # check for existing credentials in inventory
    for host_obj in norn.inventory.hosts.values():
        # set username and password if empty
        if not host_obj.username:
            c_print('Please enter device credentials:')
            host_obj.username = input("Username: ")
            host_obj.password = getpass()
            print()


# Run show commands on each switch
def get_info(task):
    c_print(f'*** {task.host}: running show comands ***')
    # run "show version" on each host
    sh_version = task.run(
        task=netmiko_send_command,
        command_string="show version",
        use_textfsm=True,
    )

    # run "show switch detail" on each host
    sh_switch = task.run(
        task=netmiko_send_command,
        command_string="show switch detail",
        use_textfsm=True,
    )

    # save show version output to task.host
    task.host['sh_version'] = sh_version.result[0]
    # pull version from show version
    task.host['current_version'] = task.host['sh_version']['version']
    # save show switch detail output to task.host
    task.host['sh_switch'] = sh_switch.result
    # init and build list of active switches in stack
    task.host['switches'] = []
    for sw in sh_switch.result:
        if sw['state'] == 'Ready':
            task.host['switches'].append(sw['switch'])


# Compare current and desired software version
def check_ver(task):

    # pull model from show version
    sw_model = task.host['sh_version']['hardware'][0].split("-")
    sw_model = sw_model[1]
    task.host['sw_model'] = sw_model

    # upgraded image to be used
    desired = task.host[sw_model]['upgrade_version']
    # record current software version
    current = task.host['current_version']

    # compare current with desired version
    if current == desired:
        c_print(f"*** {task.host}: running {current} upgrade NOT needed ***")
        # set host upgrade flag to False
        task.host['upgrade'] = False
    else:
        c_print(f"*** {task.host}: running {current} must be upgraded ***")
        # set host upgrade flag to True
        task.host['upgrade'] = True


# Stack upgrader main function
def stack_upgrader(task):
    sw_model = task.host['sw_model']
    if task.host['upgrade'] == True:
        # run function to upgrade
        c_print(f"*** {task.host}: Upgraging Catalyst {sw_model} software ***")
        

        upgrade_img = task.host[sw_model]['upgrade_img']
        cmd = f"archive download-sw /imageonly /allow-feature-upgrade /safe \
            http://{task.host['http_ip']}:8000/{upgrade_img}"

    # run upgrade command on switch stack
    upgrade_sw = task.run(
        task=netmiko_send_command,
        use_timing=True,
        command_string=cmd,
        delay_factor=25,
        max_loops=2500
    )

    # print upgrade results
    result = upgrade_sw.result.splitlines()
    for line in result:
        if "error" in line.lower() or "installed" in line.lower():
            c_print(f"*** {task.host}: {line} ***")


def upgrade_3650(task):
    c_print(f"*** {task.host}: Upgraging Catalyst 3650 software ***")
    upgrade_img = task.host['upgrade_img']
    
    if task.host['current_version'].startswith("16"):
        print("16.x")
        cmd = f"request platform software package install switch all file \
            http://{task.host['http_ip']}:8000/{upgrade_img} new auto-copy"
    else:
        print("NOT 16.x")
        cmd = f"archive download-sw /imageonly /allow-feature-upgrade /safe \
            http://{task.host['http_ip']}:8000/{upgrade_img}"

    # run upgrade command on switch stack
    upgrade_sw = task.run(
        task=netmiko_send_command,
        use_timing=True,
        command_string=cmd,
        delay_factor=25,
        max_loops=2500
    )

    # print upgrade results
    #print(upgrade_sw.result)

    statuses = ['error','installed','fail','success']
    result = upgrade_sw.result.splitlines()
    for line in result:
        for status in statuses:
            if status in line.lower():
                c_print(f"*** {task.host}: {line} ***")


def upgrade_9300(task):
    print(f"{task.host}: Upgraging Catalyst 9300 software.")
    upgrade_img = task.host['upgrade_img']
    cmd = f"request platform software package install switch all file \
        http://{task.host['http_ip']}:8000/{upgrade_img} on-reboot"

    # run upgrade command on switch stack
    upgrade_sw = task.run(
        task=netmiko_send_command,
        use_timing=True,
        command_string=cmd,
        delay_factor=25,
        max_loops=2500
    )

    # print upgrade results
    result = upgrade_sw.result.splitlines()
    for line in result:
        if "error" in line.lower() or "installed" in line.lower():
            c_print(f"*** {task.host}: {line} ***")


# Reload switches
def reload_sw(task):

    confirm = "YES"
    """
    #confirm = input("All switches are ready for reload.\n
    # Proceed with reloading all selected switches?\n
    # Type 'YES' to continue:\n")
    """
    if confirm == "YES":
        print("\n*** RELOADING ALL SELECTED SWITCHES ***\n")

    # Check if upgrade reload needed
    if task.host['upgrade'] == True:
        print(f"{task.host} reloading...")

        reload = task.run(
            task=netmiko_send_command,
            command_string="reload",
            use_timing=True,
        )        
        
        # Confirm the reload (if 'confirm' is in the output)
        for host in reload.result:

            if 'confirm' in reload.result:
                task.run(
                    task=netmiko_send_command,
                    use_timing=True,
                    command_string="",
                )

        print_result(reload)
   

def main():
  
    # initialize The Norn
    nr = InitNornir()
    # filter The Norn
    nr = nr.filter(platform="cisco_ios")
    # run The Norn kickoff
    kickoff(nr)
    
    # Start the threaded HTTP server
    c_print("Starting HTTP server")
    # change directory to images
    os.chdir("/images")
    # set http server ip
    http_svr = nr.inventory.defaults.data['http_ip']
    # init http server
    server = ThreadedHTTPServer(http_svr, 8000)
    # start http server
    server.start()
    print('~'*80)

    # gather switch info
    c_print('Gathering device configurations')
    # run The Norn to get info
    nr.run(task=get_info)
    print('~'*80)

    # checking switch version
    c_print('Check switch software version')
    # run The Norn version check
    nr.run(task=check_ver)
    print('~'*80)

   # upgrade switch software
    c_print('Upgrading Catalyst switch stack software')
    # run The Norn model check
    nr.run(task=stack_upgrader)
    print('~'*80)

    # run The Norn file copy
    #nr.run(task=file_copy)
    # run The Norn set boot
    #nr.run(task=set_boot)
    # run The Norn reload
    #nr.run(task=reload_sw)


    # Close the server
    server.stop()
    c_print("Stopping HTTP server")
    # print failed hosts
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print('~'*80)



if __name__ == "__main__":
    main()
