import ctypes
import urllib.request
import base64
import json
import hashlib
import struct
import random
import base58

from config import RPC_URL, RPC_USER, RPC_PASS


################################################################################
# CTypes and utility functions
################################################################################
class CParams(ctypes.Structure):
    _fields_ = [("hashRounds", ctypes.c_uint32),
                ("MillerRabinRounds", ctypes.c_uint32)
                ]


class uint1024(ctypes.Structure):
    _fields_ = [("data", ctypes.c_uint64 * 16)]


class uint256(ctypes.Structure):
    _fields_ = [("data", ctypes.c_uint64 * 4)]


def uint256ToInt(m):
    ans = 0
    for idx, a in enumerate(m):
        ans += a << (idx * 64)
    return ans


def uint1024ToInt(m):
    ans = 0

    if hasattr(m, 'data'):
        for idx in range(16):
            ans += m.data[idx] << (idx * 64)
    else:
        for idx, a in enumerate(m):
            ans += a << (idx * 64)

    return ans


def IntToUint1024(m):
    ans = [0] * 16
    n = int(m)
    MASK = (1 << 64) - 1

    for idx in range(16):
        ans[idx] = (m >> (idx * 64)) & MASK

    return (ctypes.c_uint64 * 16)(*ans)


def hashToArray(Hash):
    if Hash == 0:
        return [0, 0, 0, 0]

    number = int(Hash, 16)
    MASK = (1 << 64) - 1
    arr = [(number >> 64 * (jj)) & MASK for jj in range(0, 4)]

    return arr


################################################################################
# Bitcoin Daemon JSON-HTTP RPC
################################################################################
def rpc(method, params=None):
    rpc_id = random.getrandbits(32)
    data = json.dumps({"id": rpc_id, "method": method, "params": params}).encode()
    auth = base64.encodebytes((RPC_USER + ":" + RPC_PASS).encode()).decode().strip()

    request = urllib.request.Request(RPC_URL, data, {"Authorization": "Basic {:s}".format(auth)})

    with urllib.request.urlopen(request) as f:
        response = json.loads(f.read())

    if response['id'] != rpc_id:
        raise ValueError("Invalid response id: got {}, expected {:u}".format(response['id'], rpc_id))
    elif response['error'] is not None:
        raise ValueError("RPC error: {:s}".format(json.dumps(response['error'])))

    return response['result']


################################################################################
# Bitcoin Daemon RPC Call Wrappers
################################################################################
def rpc_getblocktemplate():
    try:
        return rpc("getblocktemplate", [{"rules": ["segwit"]}])
    except ValueError:
        return {}


def rpc_submitblock(block_submission):
    return rpc("submitblock", [block_submission])


def rpc_getblockcount():
    return rpc("getblockcount")


################################################################################
# Representation Conversion Utility Functions
################################################################################
def int2lehex(value, width):
    return value.to_bytes(width, byteorder='little').hex()


def int2varinthex(value):
    if value < 0xfd:
        return int2lehex(value, 1)
    elif value <= 0xffff:
        return "fd" + int2lehex(value, 2)
    elif value <= 0xffffffff:
        return "fe" + int2lehex(value, 4)
    else:
        return "ff" + int2lehex(value, 8)


def bitcoinaddress2hash160(addr):
    table = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

    hash160 = 0
    addr = addr[::-1]
    for i, c in enumerate(addr):
        hash160 += (58 ** i) * table.find(c)

    hash160 = "{:050x}".format(hash160)

    return hash160[2:50 - 8]


################################################################################
# Transaction Coinbase and Hashing Functions
################################################################################
def tx_encode_coinbase_height(height):
    width = (height.bit_length() + 7) // 8

    return bytes([width]).hex() + int2lehex(height, width)


def make_P2PKH_from_public_key(publicKey):
    from hashlib import sha256 as sha256

    address = sha256(bytes.fromhex(publicKey)).hexdigest()
    address = hashlib.new('ripemd160', bytes.fromhex(address)).hexdigest()
    address = bytes.fromhex("00" + address)
    addressCS = sha256(address).hexdigest()
    addressCS = sha256(bytes.fromhex(addressCS)).hexdigest()
    addressCS = addressCS[:8]
    address = address.hex() + addressCS
    address = base58.b58encode(bytes.fromhex(address))

    return address


def tx_make_coinbase(coinbase_script, pubkey_script, value, height, wit_commitment):
    coinbase_script = tx_encode_coinbase_height(height) + coinbase_script

    tx = ""
    # version
    tx += "02000000"
    # in-counter
    tx += "01"
    # input[0] prev hash
    tx += "0" * 64
    # input[0] prev seqnum
    tx += "ffffffff"
    # input[0] script len
    tx += int2varinthex(len(coinbase_script) // 2)
    # input[0] script
    tx += coinbase_script
    # input[0] seqnum
    tx += "00000000"
    # out-counter
    tx += "02"
    # output[0] value
    tx += int2lehex(value, 8)
    # output[0] script len
    tx += int2varinthex(len(pubkey_script) // 2)
    # output[0] script
    tx += pubkey_script
    # witness commitment value
    tx += int2lehex(0, 8)
    # witness commitment script len
    tx += int2varinthex(len(wit_commitment) // 2)
    # witness commitment script
    tx += wit_commitment
    # lock-time
    tx += "00000000"

    return tx


def tx_compute_hash(tx):
    return hashlib.sha256(hashlib.sha256(bytes.fromhex(tx)).digest()).digest()[::-1].hex()


def tx_compute_merkle_root(tx_hashes):
    tx_hashes = [bytes.fromhex(tx_hash)[::-1] for tx_hash in tx_hashes]

    while len(tx_hashes) > 1:
        if len(tx_hashes) % 2 != 0:
            tx_hashes.append(tx_hashes[-1])

        tx_hashes_new = []

        for i in range(len(tx_hashes) // 2):
            concat = tx_hashes.pop(0) + tx_hashes.pop(0)
            concat_hash = hashlib.sha256(hashlib.sha256(concat).digest()).digest()
            tx_hashes_new.append(concat_hash)

        tx_hashes = tx_hashes_new

    return tx_hashes[0][::-1].hex()


################################################################################
# Bitcoin Core Wrappers
################################################################################
class CBlock(ctypes.Structure):
    blocktemplate = {}
    _hash = "0" * 32
    _fields_ = [("nP1",                 ctypes.c_uint64 * 16),
                ("hashPrevBlock",       ctypes.c_uint64 * 4),
                ("hashMerkleRoot",      ctypes.c_uint64 * 4),
                ("nNonce",   ctypes.c_uint64),
                ("wOffset",  ctypes.c_int64),
                ("nVersion", ctypes.c_uint32),
                ("nTime",    ctypes.c_uint32),
                ("nBits",    ctypes.c_uint16),
                ]

    def get_next_block_to_work_on(self):
        blocktemplate = rpc_getblocktemplate()
        self.blocktemplate = blocktemplate
        if blocktemplate == {}:
            return self
        prevBlock = blocktemplate["previousblockhash"]
        prevBlock = hashToArray(prevBlock)

        merkleRoot = blocktemplate["merkleroothash"]
        merkleRoot = hashToArray(merkleRoot)

        self.nP1 = (ctypes.c_uint64 * 16)(*([0] * 16))
        self.hashPrevBlock = (ctypes.c_uint64 * 4)(*prevBlock)
        self.hashMerkleRoot = (ctypes.c_uint64 * 4)(*merkleRoot)
        self.nNonce = 0
        self.nTime = ctypes.c_uint32(blocktemplate["curtime"])
        self.nVersion = ctypes.c_uint32(blocktemplate["version"])
        self.nBits = ctypes.c_uint16(blocktemplate["bits"])
        self.wOffset = 0

        return self

    def serialize_block_header(self):
        nP1 = hex(uint1024ToInt(self.nP1))[2:].zfill(256)
        hashPrevBlock = hex(uint256ToInt(self.hashPrevBlock))[2:].zfill(64)
        hashMerkleRoot = hex(uint256ToInt(self.hashMerkleRoot))[2:].zfill(64)
        nNonce = struct.pack("<Q", self.nNonce)
        wOffset = struct.pack("<q", self.wOffset)
        nVersion = struct.pack("<L", self.nVersion)
        nTime = struct.pack("<L", self.nTime)
        nBits = struct.pack("<H", self.nBits)

        nP1 = bytes.fromhex(nP1)[::-1]
        hashPrevBlock = bytes.fromhex(hashPrevBlock)[::-1]
        hashMerkleRoot = bytes.fromhex(hashMerkleRoot)[::-1]

        CBlock1 = bytes()
        CBlock1 += nP1
        CBlock1 += hashPrevBlock
        CBlock1 += hashMerkleRoot
        CBlock1 += nNonce
        CBlock1 += wOffset
        CBlock1 += nVersion
        CBlock1 += nTime
        CBlock1 += nBits

        return CBlock1

    def __str__(self):
        nP1 = hex(uint1024ToInt(self.nP1))[2:].zfill(256)
        hashPrevBlock = hex(uint256ToInt(self.hashPrevBlock))[2:].zfill(64)
        hashMerkleRoot = hex(uint256ToInt(self.hashMerkleRoot))[2:].zfill(64)
        nNonce = struct.pack("<Q", self.nNonce).hex()
        wOffset = struct.pack("<q", self.wOffset).hex()
        nVersion = struct.pack("<L", self.nVersion).hex()
        nTime = struct.pack("<L", self.nTime).hex()
        nBits = struct.pack("<H", self.nBits).hex()

        nP1 = bytes.fromhex(nP1)[::-1].hex()
        hashPrevBlock = bytes.fromhex(hashPrevBlock)[::-1].hex()
        hashMerkleRoot = bytes.fromhex(hashMerkleRoot)[::-1].hex()

        s = "CBlock class: \n"
        s += "                    nP1: " + str(nP1) + "\n"
        s += "          hashPrevBlock: " + str(hashPrevBlock) + "\n"
        s += "         hashMerkleRoot: " + str(hashMerkleRoot) + "\n"
        s += "                 nNonce: " + str(nNonce) + "\n"
        s += "                wOffset: " + str(wOffset) + "\n"
        s += "               nVersion: " + str(nVersion) + "\n"
        s += "                  nTime: " + str(nTime) + "\n"
        s += "                  nBits: " + str(nBits) + "\n"

        return s

    def int2lehex(self, value, width):
        return value.to_bytes(width, byteorder='little').hex()

    def int2varinthex(self, value):
        if value < 0xfd:
            return self.int2lehex(value, 1)
        elif value <= 0xffff:
            return "fd" + self.int2lehex(value, 2)
        elif value <= 0xffffffff:
            return "fe" + self.int2lehex(value, 4)
        else:
            return "ff" + self.int2lehex(value, 8)

    def prepare_block_for_submission(self):
        submission = self.serialize_block_header().hex()

        submission += self.int2varinthex(len(self.blocktemplate['transactions']))

        for tx in self.blocktemplate['transactions']:
            submission += tx['data']

        return submission

    def rpc_submitblock(self):
        submission = self.prepare_block_for_submission()

        return rpc_submitblock(submission), submission

    def compute_raw_hash(self):
        return hashlib.sha256(hashlib.sha256(self.serialize_block_header()).digest()).digest()[::-1]
