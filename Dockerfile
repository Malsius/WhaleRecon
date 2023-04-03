FROM kalilinux/kali-rolling

RUN apt update
RUN apt install -y git python3 python3-pip seclists curl dnsrecon enum4linux feroxbuster gobuster impacket-scripts nbtscan nikto nmap onesixtyone oscanner redis-tools smbclient smbmap snmp sslscan sipvicious tnscmd10g whatweb wkhtmltopdf hydra nfs-common dnsutils
RUN pip install git+https://github.com/Tib3rius/AutoRecon
RUN pip install git+https://github.com/Malsius/autorecon-reporting