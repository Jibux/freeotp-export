# FreeOTP export

## Usage

```
./freeotp-export.py -h
```

## Manual process

### Backup

```
adb backup -f freeotp-backup.ab -apk org.fedorahosted.freeotp
```

### Extract tokens.xml from backup

(printf "\x1f\x8b\x08\x00\x00\x00\x00\x00" && dd if=freeotp-backup.ab bs=1 skip=24) | gunzip -c | tar -xvO apps/org.fedorahosted.freeotp/sp/tokens.xml 

## Sources
* https://gist.github.com/kontez/05923f2fc208c6bbe3de81f28de571db
* https://github.com/viljoviitanen/freeotp-export

