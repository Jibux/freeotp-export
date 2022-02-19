#!/usr/bin/python3


import base64, json, html, sys, os
import xml.etree.ElementTree as ET
import qrcode
import urllib.parse
import argparse
import subprocess
import zlib
import tarfile, io
import shutil
from pathlib import Path
from fpdf import FPDF


FREEOTP_BACKUP = 'freeotp-backup.ab'
APK_NAME = 'org.fedorahosted.freeotp'
TOKENS_FILE = 'tokens.xml'
APK_ROOT = 'apps'
APK_PATH = f'{APK_ROOT}/{APK_NAME}/sp/{TOKENS_FILE}'
PDF_FILE = 'qrcodes.pdf'
IMAGES_DIR='qrcodes'
QRCODE_W = 35
QRCODE_H = 35


def fail(msg = "Something went wrong..."):
    print(msg, file = sys.stderr)
    sys.exit(1)


def create_dir_if_not_exists(d):
    if not d.is_dir():
        print(f"Create {d} directory")
        d.mkdir()


def backup_freeotp(workdir):
    create_dir_if_not_exists(workdir)
    backup_path = workdir / FREEOTP_BACKUP
    print(f"Backup freeotp to {backup_path}")
    ret = subprocess.call(['adb', 'backup', '-f', backup_path, '-apk', APK_NAME])
    if ret != 0 or backup_path.stat().st_size == 0:
        fail("Backup freeotp failed!")


def extract_tokens_file(workdir):
    backup_path = workdir / FREEOTP_BACKUP
    tokens_file = workdir / APK_PATH

    if not (backup_path.is_file() and backup_path.stat().st_size > 0):
        backup_freeotp(workdir)

    print(f'Export tokens file to {tokens_file} using freeotp backup from {backup_path}')
    with open(backup_path, 'rb') as f:
        f.seek(24)  # skip 24 bytes
        data = f.read()  # read the rest
        tarstream = zlib.decompress(data)
        with tarfile.open(fileobj=io.BytesIO(tarstream)) as tf:
            tf.extract(APK_PATH, path=workdir)

    if not tokens_file.is_file():
        fail("Tokens file failed to be extracted!")


def parse_tokens_from_xml(workdir):
    tokens = []
    token_order = []
    tokens_file = workdir / APK_PATH

    if not tokens_file.is_file():
        extract_tokens_file(workdir)

    root = ET.parse(str(tokens_file)).getroot()
    for secrets in root.findall("string"):
        name = secrets.get("name")
        if name == "tokenOrder":
            continue

        tokens.append(json.loads(secrets.text))
    token_order.append(name)
    #json.dump({"tokenOrder": token_order, "tokens": tokens}, sys.stdout)
    #print('')

    return tokens


def secret_to_b32(secret):
    sec = bytes((x + 256) & 255 for x in secret)
    code = base64.b32encode(sec)
    return code.decode()


def query_data(p):
    return "&".join([f'{urllib.parse.quote(d)}={urllib.parse.quote(p[d])}' for d in p ])


def generate_images(images_path, tokens):
    i = 0
    qrcode_list = []

    print(f"Generate QR Code images to {images_path}")

    create_dir_if_not_exists(images_path)

    for token in tokens:
        # print('===')
        # print(token)
        if token.get('issuerInt'):
            issuer = token['issuerInt']
        elif token.get('issuerExt'):
            issuer = token['issuerExt']
        elif token.get('issuerAlt'):
            issuer = token['issuerAlt']
        elif token.get('labelAlt'):
            issuer = token['labelAlt']
        else:
            issuer = f'Unknown{i}';
        b32_secret = secret_to_b32(token['secret'])
        # print(f'Secret b32: {b32_secret}')
        param = {
          'secret'    : b32_secret,
          'issuer'    : issuer,
          'algorithm' : token['algo'],
          'digits'    : str(token['digits']),
          'period'    : str(token['period']),
        }
        label = f'{token["issuerExt"]}:{token["label"]}' if (token.get('issuerExt')) else token['label'];
        uri = f'otpauth://{token["type"].lower()}/{urllib.parse.quote(label)}?{query_data(param)}';
        # print(f'URI: {uri}')
        img = qrcode.make(uri)
        file_path = str(images_path / f"{i}.png")
        img.save(f'{file_path}')
        qrcode_list.append((label, file_path))
        i = i + 1

    return qrcode_list


def clean(workdir):
    print(f"Clean {workdir} workdir")
    remove_path(workdir, FREEOTP_BACKUP)
    remove_path(workdir, APK_ROOT)
    remove_path(workdir, IMAGES_DIR)


def add_image(pdf, image, text, x, y):
    pdf.image(image, x, y, QRCODE_W, QRCODE_H)
    pdf.text(x, y + QRCODE_H + 2, f'{text}')


def write_to_pdf_file(pdf, qrcode_list):
    x = 10
    y = 10
    for qc in qrcode_list:
        if x > 150:
            x = 10
            y = y + QRCODE_H + 13
        if y > 250:
            pdf.add_page()
            x = 10
            y = 10

        add_image(pdf, f'{qc[1]}', f'{qc[0]}', x, y)
        x = x + QRCODE_W + 60


def generate_doc(pdf_path, qrcode_list):
    if pdf_path.is_file():
        pdf_path.unlink()

    pdf = FPDF()
    pdf.set_font('Arial', '', 8)
    pdf.add_page()
    write_to_pdf_file(pdf, qrcode_list)
    pdf.output(pdf_path, "F")
    print(f"QR Codes written to {pdf_path}")


def remove_path(workdir, f):
    path = workdir / f
    if path.is_file():
        path.unlink()
        print(f"{path} file removed")
    elif path.is_dir():
        shutil.rmtree(path)
        print(f"{path} dir removed")


def main():
    default_workdir = os.path.realpath('.')
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    parser.add_argument('-w', '--workdir',
            help='Work directory (defaults to current dir)', type=str,
            default=default_workdir)
    parser.add_argument('-b', '--backup', help='Backup freeotp app',
            action="store_true")
    parser.add_argument('-t', '--tokens', help='Extract tokens file from freeotp backup',
            action="store_true")
    parser.add_argument('-q', '--qrcodes', help='Get qrcodes from tokens file and write them to PDF',
            action="store_true")
    group.add_argument('-c', '--clean', help='Clean all generated files (done by default after PDF generation)',
            action="store_true")
    group.add_argument('-C', '--noclean', help='Do not clean after PDF generation',
            action="store_true")
    args = parser.parse_args()
    workdir = Path(args.workdir)
    print(f"Work directory: {workdir}")
    if args.backup:
        backup_freeotp(workdir)
    elif args.tokens:
        extract_tokens_file(workdir)
    elif args.qrcodes:
        tokens = parse_tokens_from_xml(workdir)
        qrcode_list = generate_images(workdir / IMAGES_DIR, tokens)
        qrcode_list_sorted = sorted(qrcode_list, key=lambda qc: qc[0])
        generate_doc(workdir / PDF_FILE, qrcode_list_sorted)
        if not args.noclean:
            clean(workdir)
    elif args.clean:
        clean(workdir)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()

