#!/usr/bin/python3
'''
This script is uses the Nornir framework to verify the software version on 
Cisco Catalyst 3750 and 3650 switch stacks.

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

import os, sys
from getpass import getpass
from nornir import InitNornir
from nornir.plugins.tasks.networking import netmiko_send_command
from nornir.plugins.tasks.networking import netmiko_save_config


# Print formatting function
def c_print(printme):
    # Print centered text with newline before and after
    print(f"\n" + printme.center(80, ' ') + "\n")


# Set device credentials
def kickoff(norn, username=None, password=None):
    # print banner
    print()
    print('~'*80)
    c_print('This script will verify the software version on Cisco Catalyst switch stacks')
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

    # run "show boot" on each host
    sh_boot = task.run(
        task=netmiko_send_command,
        command_string="show boot",
        use_textfsm=True,
    )
    # save show boot version output to task.host
    task.host['sh_boot'] = sh_boot.result[0]['boot_path'].split("/")[-1]


# Compare current and desired software version
def check_ver(task):
    sw_model = task.host['sw_model']
    # upgraded image to be used
    desired = task.host[sw_model]['upgrade_version']
    # record current software version
    current = task.host['current_version']

    upgrade_img = task.host[sw_model]['upgrade_img']

    # compare current with desired version
    if current == desired:
        print(f"{' ' *10}*** {task.host}: running {current} upgrade NOT needed ***")
        # set host upgrade flag to False
        task.host['upgrade'] = False
    else:
        print(f"{' ' *10}*** {task.host}: running {current} must be upgraded ***")
        # set host upgrade flag to True
        task.host['upgrade'] = True

        if '3750' in sw_model:
            boot_ver = ".".join(task.host['sh_boot'].split(".")[-3:-1])

            upgrade_ver = ".".join(upgrade_img.split(".")[-3:-1])

            if boot_ver == upgrade_ver:
                print(f"{' ' *10}*** {task.host}: will be upgraded to {desired} on next reboot ***")

        elif '3650' in sw_model or '3850' in sw_model:
            _stuff = None


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
                f"ftp://{task.host['ftp_ip']}/{upgrade_img}"

        elif '3650' in sw_model or '3850' in sw_model:
            if task.host['current_version'].startswith("16"):
                cmd = f"request platform software package install switch all file " + \
                    f"ftp://{task.host['ftp_ip']}/{upgrade_img} new auto-copy"
            else:
                cmd = f"archive download-sw /imageonly /allow-feature-upgrade /safe " + \
                    f"ftp://{task.host['ftp_ip']}/{upgrade_img}"

        elif '9300' in sw_model:
                cmd = f"request platform software package install switch all file " + \
                    f"ftp://{task.host['ftp_ip']}/{upgrade_img} on-reboot"

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
    nr.run(task=check_ver, num_workers=1)
    # print failed hosts
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print('~'*80)


if __name__ == "__main__":
    main()
