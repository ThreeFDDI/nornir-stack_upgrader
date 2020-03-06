#!/usr/local/bin/python3
'''
Just HTTP server for testing
'''

import threading
import socketserver
import os, sys, time, socket
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

 
    # Start the threaded HTTP server
    os.chdir("images")
    
    print("Starting HTTP server.")
    server = ThreadedHTTPServer('10.165.13.125', 8000)
    server.start()

    import ipdb; ipdb.set_trace()

    # Close the server
    server.stop()
    print("Stopping HTTP server.")
