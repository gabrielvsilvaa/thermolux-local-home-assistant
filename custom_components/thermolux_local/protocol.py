"""Thermolux Easy-IV local TCP protocol."""
import socket

PORT = 8090
MODES = ("parado", "amaciar", "secar", "esterilizar", "degelo", "aquecimento", "timer")
COMMANDS = {"parado": 23, "amaciar": 17, "secar": 18, "esterilizar": 19, "degelo": 21, "aquecimento": 20}
TEMPERATURES = {
    "20 °C · Modo Eco": "aquecimento",
    "40 °C · Baixa Temp": "amaciar",
    "50 °C · Alta Temp": "secar",
    "60 °C · Esterilizar": "esterilizar",
}


def read_exact(connection, size):
    data = bytearray()
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            raise OSError("Resposta incompleta do Thermolux")
        data.extend(chunk)
    return bytes(data)


def exchange(host, code, size):
    with socket.create_connection((host, PORT), timeout=2) as connection:
        connection.sendall(bytes([90, 165, code, 1, 0, 0, code]))
        reply = read_exact(connection, size)
    if reply[:4] != bytes([90, 165, code, 2]):
        raise OSError("Resposta inesperada do Thermolux")
    return reply


def read_mode(host):
    reply = exchange(host, 0x21, 7)
    if not any(reply[4:6]) or reply[6] >= len(MODES):
        raise OSError("Modo inválido")
    return MODES[reply[6]]


def read_identity(host):
    reply = exchange(host, 0x23, 13)
    if reply[4:6] != b"\x00\x06" or sum(reply[:-1]) % 256 != reply[-1]:
        raise OSError("Identificação inválida")
    return reply[6:12].hex()


def set_mode(host, mode):
    code = COMMANDS[mode]
    reply = exchange(host, code, 8)
    if reply[4:] != bytes([0, 1, 1, (code + 3) % 256]):
        raise OSError("O Thermolux não confirmou o comando")
