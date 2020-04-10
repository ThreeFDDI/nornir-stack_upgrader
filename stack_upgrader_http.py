#!/usr/bin/python3
'''
This script is used to upgrade software on Cisco Catalyst 3750 and 3650 switch stacks.

Required variables:

C3750V2:
    upgrade_version: '12.2(55)SE12'
    upgrade_img: 'c3750-ipservicesk9-tar.122-55.SE12.tar'
C3750X:
    upgrade_version: '15.2(4)E8'
    upgrade_img: 'c3750e-universalk9-tar.152-4.E8.tar'
C3650:
    upgrade_version: '16.9.4'
    upgrade_img: 'cat3k_caa-universalk9.16.09.04.SPA.bin'
C9300:  
    upgrade_version: '16.9.4'
    upgrade_img: 'cat9k_iosxe.16.09.04.SPA.bin'

'''

import threading
import socketserver
import os, sys, time, socket
from getpass import getpass
from nornir import InitNornir
from nornir.plugins.tasks.networking import netmiko_send_command
from nornir.plugins.tasks.networking import netmiko_save_config
from http.server import SimpleHTTPRequestHandler


# HTTP server for file transfer
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


# Print formatting function
def c_print(printme):
    # Print centered text with newline before and after
    print(f"\n" + printme.center(80, ' ') + "\n")


# Continue banner
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


# Set device credentials
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

    # save show version output to task.host
    task.host['sh_version'] = sh_version.result[0]
    # pull version from show version
    task.host['current_version'] = task.host['sh_version']['version']

    # pull model from show version
    sw_model = task.host['sh_version']['hardware'][0].split("-")
    sw_model = sw_model[1]
    task.host['sw_model'] = sw_model


# Compare current and desired software version
def check_ver(task):
    sw_model = task.host['sw_model']
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
    upgrade_img = task.host[sw_model]['upgrade_img']
    if task.host['upgrade'] == True:
        # run function to upgrade
        c_print(f"*** {task.host}: Upgraging Catalyst {sw_model} software ***")

        # upgrade commands based on switch hardware model 
        if '3750' in sw_model:
            cmd = f"archive download-sw /imageonly /allow-feature-upgrade /safe " + \
                f"http://{task.host['http_ip']}:8000/{upgrade_img}"

        elif '3650' in sw_model or '3850' in sw_model:
            if task.host['current_version'].startswith("16"):
                cmd = f"request platform software package install switch all file " + \
                    f"http://{task.host['http_ip']}:8000/{upgrade_img} new auto-copy"
            else:
                cmd = f"archive download-sw /imageonly /allow-feature-upgrade /safe " + \
                    f"http://{task.host['http_ip']}:8000/{upgrade_img}"

        elif '9300' in sw_model:
                cmd = f"request platform software package install switch all file " + \
                    f"http://{task.host['http_ip']}:8000/{upgrade_img} on-reboot"

    print(cmd)
    print()

    # run upgrade command on switch stack
    upgrade_sw = task.run(
        task=netmiko_send_command,
        use_timing=True,
        command_string=cmd,
        delay_factor=150,
        #max_loops=1000
    )
    # print upgrade results
    statuses = ['error','installed','fail','success']
    result = upgrade_sw.result.splitlines()
    for line in result:
        for status in statuses:
            if status in line.lower():
                print(f"{task.host}: {line}")


# Reload switches
def reload_sw(task):
    # Check if upgrade reload needed
    if task.host['upgrade'] == True:
        c_print(f"*** {task.host} is reloading ***")
        
        # save config
        task.run(
            task=netmiko_save_config,
        )
        # send reload command
        reload = task.run(
            task=netmiko_send_command,
            command_string="reload",
            use_timing=True,
        )        
        # confirm if needed
        if 'confirm' in reload.result:
            task.run(
                task=netmiko_send_command,
                use_timing=True,
                command_string="",
            )


def main():
  
    # initialize The Norn
    nr = InitNornir()
    # filter The Norn
    nr = nr.filter(platform="cisco_ios")
    # run The Norn kickoff
    kickoff(nr)
    
    # start the threaded HTTP server
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
    # print failed hosts
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print('~'*80)

    # checking switch version
    c_print('Checking switch software versions')
    # run The Norn version check
    nr.run(task=check_ver)
    # print failed hosts
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print('~'*80)

   # upgrade switch software
    c_print('Upgrading Catalyst switch stack software')
    # prompt to proceed
    proceed()
    # run The Norn model check
    nr.run(task=stack_upgrader, num_workers=1)
    # print failed hosts
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print('~'*80)

   # upgrade switch software
    c_print('Rebooting Catalyst switch stacks')
    # prompt to proceed
    proceed()
    # run The Norn reload
    nr.run(task=reload_sw)
    print('~'*80)

    # shut down the HTTP server
    server.stop()
    c_print("Stopping HTTP server")
    # print failed hosts
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print('~'*80)


if __name__ == "__main__":
    main()
