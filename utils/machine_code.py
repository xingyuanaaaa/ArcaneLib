# -*- coding: utf-8 -*-
# 软件库系统 - 机器码模块
# 通过采集硬件信息生成唯一机器码，用于卡密绑定

import hashlib
import uuid
import platform
import subprocess
import os
import re


def _get_mac_addresses():
    """获取所有网卡MAC地址"""
    mac_list = []
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(['getmac'], capture_output=True, text=True, shell=True)
            macs = re.findall(r'([0-9A-F]{2}[-][0-9A-F]{2}[-][0-9A-F]{2}[-][0-9A-F]{2}[-][0-9A-F]{2}[-][0-9A-F]{2})', result.stdout, re.IGNORECASE)
            mac_list = [mac.replace('-', ':').upper() for mac in macs if mac.replace('-', '') != '000000000000']
        else:
            result = subprocess.run(['ifconfig'], capture_output=True, text=True)
            macs = re.findall(r'([0-9A-F]{2}[:][0-9A-F]{2}[:][0-9A-F]{2}[:][0-9A-F]{2}[:][0-9A-F]{2}[:][0-9A-F]{2})', result.stdout, re.IGNORECASE)
            mac_list = [mac.upper() for mac in macs if mac.replace(':', '') != '000000000000']
    except Exception:
        pass

    if not mac_list:
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                        for elements in range(0, 2 * 6, 8)][::-1])
        mac_list = [mac.upper()]

    return mac_list


def _get_cpu_info():
    """获取CPU信息"""
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(['wmic', 'cpu', 'get', 'ProcessorId'], capture_output=True, text=True, shell=True)
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                return lines[1].strip()
        else:
            result = subprocess.run(['cat', '/proc/cpuinfo'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'Serial' in line or 'processor' in line:
                    return line.strip()
    except Exception:
        pass
    return platform.processor() or 'UnknownCPU'


def _get_disk_serial():
    """获取硬盘序列号"""
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(['wmic', 'diskdrive', 'get', 'SerialNumber'], capture_output=True, text=True, shell=True)
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                return lines[1].strip()
        else:
            result = subprocess.run(['lsblk', '-o', 'SERIAL'], capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                return lines[1].strip()
    except Exception:
        pass
    return 'UnknownDisk'


def _get_motherboard_serial():
    """获取主板序列号"""
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(['wmic', 'baseboard', 'get', 'SerialNumber'], capture_output=True, text=True, shell=True)
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                return lines[1].strip()
        else:
            result = subprocess.run(['dmidecode', '-s', 'baseboard-serial-number'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
    except Exception:
        pass
    return 'UnknownMB'


def get_machine_code():
    """
    生成机器码
    采集MAC地址 + CPU + 硬盘 + 主板信息
    返回32位哈希值
    """
    macs = _get_mac_addresses()
    primary_mac = macs[0] if macs else '00:00:00:00:00:00'

    cpu_id = _get_cpu_info()
    disk_serial = _get_disk_serial()
    mb_serial = _get_motherboard_serial()

    fingerprint = f"{primary_mac}|{cpu_id}|{disk_serial}|{mb_serial}|{platform.node()}"

    code = hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:32].upper()
    formatted = '-'.join([code[i:i+4] for i in range(0, 32, 4)])
    return formatted


def get_machine_code_short():
    """获取简短机器码（16位）"""
    full_code = get_machine_code().replace('-', '')
    return full_code[:16]


def verify_machine_code(stored_code, current_code):
    """验证机器码是否匹配"""
    return stored_code.replace('-', '').upper() == current_code.replace('-', '').upper()


def get_machine_fingerprint():
    """获取机器指纹（用于客户端-服务端验证）"""
    import time
    from config import MACHINE_CODE_SALT
    raw = f"{get_machine_code()}:{MACHINE_CODE_SALT}"
    return hashlib.sha512(raw.encode('utf-8')).hexdigest()