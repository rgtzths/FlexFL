import requests
from dotenv import load_dotenv
import os
import urllib3
import time
from rich.console import Console

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

API_URL = os.getenv("PM_API_URL")
USER = os.getenv("PM_USERNAME")
PASS = os.getenv("PM_PASSWORD")
INSECURE = True 
NODE = "frodo"
TEMPLATE = 2000

N_WORKERS = 10
PREFIX = "fl-worker"

console = Console()


def check_env_vars() -> None:
    if not all([API_URL, USER, PASS]):
        raise EnvironmentError("Please set PM_API_URL, PM_USERNAME, and PM_PASSWORD in your environment variables.")
    

def check_response(response) -> None:
    if response.status_code != 200:
        print(f"Error: {response.status_code}, {response.text}")
        raise Exception(f"Request failed with status code {response.status_code}")


def authenticate() -> dict:
    url = f"{API_URL}/access/ticket"
    data = {
        "username": USER,
        "password": PASS
    }
    response = requests.post(url, data=data, verify=not INSECURE)
    check_response(response)
    ticket = response.json()["data"]["ticket"]
    csrf_token = response.json()["data"]["CSRFPreventionToken"]
    return {
        "Authorization": f"PVEAuthCookie={ticket}",
        "CSRFPreventionToken": csrf_token,
    }
    

def next_id(headers) -> int:
    url = f"{API_URL}/cluster/nextid"
    response = requests.get(url, headers=headers, verify=not INSECURE)
    check_response(response)
    return response.json()["data"]


def create_vm(headers, vm_id, vm_name) -> None:
    vm_data = {
        "newid": vm_id,
        "name": vm_name,
        "target": "frodo",
        "pool": "leonardoalmeida",
        "full": 1,
    }

    url = f"{API_URL}/nodes/{NODE}/qemu/{TEMPLATE}/clone"
    response = requests.post(url, headers=headers, data=vm_data, verify=not INSECURE)
    check_response(response)


def wait_for_vm_creation(headers, vm_id) -> None:
    url = f"{API_URL}/nodes/{NODE}/qemu/{vm_id}/status/current"
    while True:
        response = requests.get(url, headers=headers, verify=not INSECURE)
        if response.status_code == 403:
            time.sleep(10)
            continue
        check_response(response)
        break


def setup_vm(headers, name) -> int:
    vm_id = next_id(headers)
    create_vm(headers, vm_id, name)
    console.log(f"VM: [bold cyan]{name}[/bold cyan] created with ID: {vm_id}.")
    with console.status("Waiting for VM creation..."):
        wait_for_vm_creation(headers, vm_id)
    console.log(f"VM {vm_id} creation completed.")
    return vm_id


def create_all_vms(headers) -> None:
    ids = []
    for i in range(1, N_WORKERS + 1):
        name = f"{PREFIX}-{i}"
        vm_id = setup_vm(headers, name)
        console.log(f"VM {name} is ready")
        ids.append(vm_id)
    console.log("All VMs created successfully.")
    

def main():
    check_env_vars()
    headers = authenticate()
    console.log("Authenticated successfully.")
    console.log("Creating VMs...")
    create_all_vms(headers)
    
    

if __name__ == "__main__":
    main()
