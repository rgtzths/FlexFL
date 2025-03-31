import requests
from dotenv import load_dotenv
import os
import urllib3
import urllib.parse
import time
from rich.console import Console

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

N_WORKERS = 1
PREFIX = "fl-worker"

API_URL = os.getenv("PM_API_URL")
USER = os.getenv("PM_USERNAME")
PASS = os.getenv("PM_PASSWORD")
VM_PASSWORD = os.getenv("VM_PASSWORD")
INSECURE = True 
NODE = "frodo"
POOL = "leonardoalmeida"
TEMPLATE = 2000
IDS_FILE = "scripts/ids.txt"
IPS_FILE = "scripts/ips.txt"
PUBLIC_KEY = os.getenv("HOME") + "/.ssh/id_rsa.pub"


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
    console.log("Authenticated successfully.")
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
        "target": NODE,
        "pool": POOL,
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
    with console.status("Waiting for VM cloning..."):
        wait_for_vm_creation(headers, vm_id)
    console.log(f"VM [bold cyan]{vm_id}:{name}[/bold cyan] cloning completed.")
    return vm_id


def change_specs(headers, vm_id) -> None:
    url = f"{API_URL}/nodes/{NODE}/qemu/{vm_id}/config"
    response = requests.get(url, headers=headers, verify=not INSECURE)
    check_response(response)
    data = response.json()["data"]
    net0 = data["net0"] + ",rate=50"
    with open(PUBLIC_KEY, "r") as f:
        sshkey = f.read().strip()
    sshkeys = urllib.parse.unquote(data["sshkeys"])
    sshkeys = sshkeys + f"\n\n{sshkey}\n"
    sshkeys = urllib.parse.quote(sshkeys, safe="")
    payload = {
        "net0": net0,
        "sshkeys": sshkeys,
        "cipassword": VM_PASSWORD
    }
    response = requests.put(url, headers=headers, data=payload, verify=not INSECURE)
    check_response(response)
    console.log(f"VM [bold cyan]{vm_id}[/bold cyan] specifications changed.")


def create_all_vms(headers) -> None:
    ids = []
    console.log("Creating VMs...")
    for i in range(1, N_WORKERS + 1):
        name = f"{PREFIX}-{i}"
        vm_id = setup_vm(headers, name)
        change_specs(headers, vm_id)
        ids.append(vm_id)
    console.log("All VMs created successfully.")
    with open(IDS_FILE, "w") as f:
        for vm_id in ids:
            f.write(f"{vm_id}\n")


def get_ip(headers, vm_id) -> str:
    url = f"{API_URL}/nodes/{NODE}/qemu/{vm_id}/agent/network-get-interfaces"
    while True:
        response = requests.get(url, headers=headers, verify=not INSECURE)
        if response.status_code != 500:
            break
        time.sleep(10)
    check_response(response)
    data = response.json()["data"]["result"]
    for interface in data:
        if interface.get("name", None) == "eth0":
            for ip_addr in interface.get("ip-addresses", []):
                if ip_addr["ip-address-type"] == "ipv4":
                    return ip_addr["ip-address"]
    raise Exception("No IPv4 address found for eth0.")


def wait_for_status(headers, vm_id, status) -> None:
    url = f"{API_URL}/nodes/{NODE}/qemu/{vm_id}/status/current"
    while True:
        response = requests.get(url, headers=headers, verify=not INSECURE)
        check_response(response)
        if response.json()["data"]["status"] == status:
            break


def start_vms(headers) -> None:
    with open(IDS_FILE, "r") as f:
        ids = [int(line.strip()) for line in f.readlines()]
    ips = []
    for vm_id in ids:
        url = f"{API_URL}/nodes/{NODE}/qemu/{vm_id}/status/start"
        response = requests.post(url, headers=headers, verify=not INSECURE)
        check_response(response)
        with console.status(f"Starting VM [bold cyan]{vm_id}[/bold cyan]..."):
            wait_for_status(headers, vm_id, "running")
        console.log(f"VM [bold cyan]{vm_id}[/bold cyan] started.")
        with console.status(f"Waiting for VM [bold cyan]{vm_id}[/bold cyan] IP..."):
            ip = get_ip(headers, vm_id)
        console.log(f"VM [bold cyan]{vm_id}[/bold cyan] IP: {ip}")
        ips.append(ip)
    with open(IPS_FILE, "w") as f:
        for ip in ips:
            f.write(f"{ip}\n")


def shutdown_vms(headers) -> None:
    with open(IDS_FILE, "r") as f:
        ids = [int(line.strip()) for line in f.readlines()]
    for vm_id in ids:
        url = f"{API_URL}/nodes/{NODE}/qemu/{vm_id}/status/shutdown"
        response = requests.post(url, headers=headers, verify=not INSECURE)
        check_response(response)
        with console.status(f"Stopping VM [bold cyan]{vm_id}[/bold cyan]..."):
            wait_for_status(headers, vm_id, "stopped")
        console.log(f"VM [bold cyan]{vm_id}[/bold cyan] stopped.")


def main():
    check_env_vars()
    headers = authenticate()
    # create_all_vms(headers)
    # start_vms(headers)
    # shutdown_vms(headers)

    # print(get_ip(headers, 103))
    

if __name__ == "__main__":
    main()
