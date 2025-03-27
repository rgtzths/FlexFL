terraform {
    required_providers {
        proxmox = {
            source  = "telmate/proxmox"
            version = "~> 2.9"
        }
    }
}

variable "pm_api_url" {}
variable "pm_api_token_id" {}
variable "pm_api_token_secret" {}
variable "pm_user" {}
variable "pm_password" {}

provider "proxmox" {
    pm_api_url          = var.pm_api_url
    pm_api_token_id     = var.pm_api_token_id
    pm_api_token_secret = var.pm_api_token_secret
    # pm_user             = var.pm_user
    # pm_password         = var.pm_password
    pm_tls_insecure     = true
}

resource "proxmox_vm_qemu" "terraform_vm" {
    name        = "terraform"
    target_node = "frodo"
    pool        = "leonardoalmeida"

    clone       = "2000"
    full_clone  = true

    os_type     = "cloud-init"
    cores       = 2
    memory      = 2048

    network {
        model  = "virtio"
        bridge = "vmbr0"
        rate   = 50
    }
}
