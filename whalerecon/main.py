import argparse
import docker
import os
import tempfile
import shutil

from rich.progress import Progress


def get_autorecon_cmd(autorecon_options):
    return f"autorecon {' '.join(autorecon_options)}"


# If destination dst already exists, new one will be named (x)dst
def copy_tmp(src, tmp_dir):
    src = os.path.abspath(src)
    dst_name = os.path.basename(src)
    dst_path = os.path.join(tmp_dir, dst_name)
    while os.path.exists(dst_path):
        dst_name = f"x{dst_name}"
        dst_path = os.path.join(tmp_dir, dst_name)
    try:
        if os.path.isfile(src):
            shutil.copy(src, dst_path)
        else:
            shutil.copytree(src, dst_path)
        return f"/opt/whalerecon/files/{dst_name}"
    except (PermissionError, FileNotFoundError, IsADirectoryError) as error:
        print(error)
        exit(1)


def parse_autorecon_input_files(args, tmp_files):
    result = []
    if args.target_file:
        tmp_target_file = copy_tmp(args.target_file, tmp_files)
        result.append(f"-t {tmp_target_file}")
    if args.config:
        tmp_config = copy_tmp(args.config, tmp_files)
        result.append(f"-c {tmp_config}")
    if args.global_file:
        tmp_global_file = copy_tmp(args.global_file, tmp_files)
        result.append(f"-g {tmp_global_file}")
    if args.plugins_dir:
        tmp_plugins_dir = copy_tmp(args.plugins_dir, tmp_files)
        result.append(f"--plugins-dir {tmp_plugins_dir}")
    if args.add_plugins_dir:
        tmp_add_plugins_dir = copy_tmp(args.add_plugins_dir, tmp_files)
        result.append(f"--add-plugins-dir {tmp_add_plugins_dir}")
    if getattr(args, "dirbuster.wordlist"):
        tmp_dirbuster_wordlists_option = "--dirbuster.wordlist"
        for dirbuster_wordlist in getattr(args, "dirbuster.wordlist"):
            if not os.path.exists(dirbuster_wordlist):
                tmp_dirbuster_wordlists_option = f"{tmp_dirbuster_wordlists_option} {dirbuster_wordlist}"
            else:
                tmp_dirbuster_wordlist = copy_tmp(dirbuster_wordlist, tmp_files)
                tmp_dirbuster_wordlists_option = f"{tmp_dirbuster_wordlists_option} {tmp_dirbuster_wordlist}"
        result.append(tmp_dirbuster_wordlists_option)
    if getattr(args, "global.username_wordlist"):
        tmp_global_username_wordlist = copy_tmp(getattr(args, "global.username_wordlist")[0], tmp_files)
        result.append(f"--global.username-wordlist {tmp_global_username_wordlist}")
    if getattr(args, "global.password_wordlist"):
        tmp_global_password_wordlist = copy_tmp(getattr(args, "global.password_wordlist")[0], tmp_files)
        result.append(f"--global.password-wordlist {tmp_global_password_wordlist}")
    return result


def print_help(parser, client):
    print("WhaleRecon help :")
    print(parser.format_help())
    container = client.containers.run(
        name="whalerecon",
        network_mode="host",
        working_dir="/opt/whalerecon",
        detach=True,
        image="malsius/whalerecon",
        command="bash",
        tty=True
    )
    print("AutoRecon help :")
    run_command(container, "autorecon -h")
    container.kill()
    container.remove()
    exit(0)


def run_command(container, command):
    output = container.exec_run(cmd=f"bash -c '{command}'", tty=True, stream=True)[1]
    for line in output:
        print(line.decode(), end="")
        if "Unrecognized arguments" in line.decode() or "You must specify at least one target to scan" in line.decode():
            container.kill()
            container.remove()
            exit(1)


def copy_output(output_path, tmp_results, tmp_reports):
    os.makedirs(output_path)
    shutil.copytree(tmp_results, os.path.join(output_path, "results"))
    shutil.copytree(tmp_reports, os.path.join(output_path, "reports"))


def is_valid_output(output_path):
    yes = ["yes", "y", ""]
    no = ["no", "n"]
    output_path = os.path.abspath(output_path)
    while os.path.exists(output_path):
        print(f"{output_path} already exists")
        choice = input("Would you like to change output path ? [Y/n] ")
        if choice in yes:
            output_path = input("Enter new path: ")
        elif choice in no:
            print("Abort scan")
            exit(1)
        else:
            print("Wrong choice")
    print(f"Output path: {os.path.abspath(output_path)}")
    return output_path


def pretty_pull(client):
    tasks = {}
    with Progress() as progress:
        print("Pulling from malsius/whalerecon")
        output = client.api.pull("malsius/whalerecon", stream=True, decode=True)
        for line in output:
            status = line["status"]
            if status == "Downloading":
                description = f"[red][Downloading {line['id']}]"
            elif status == "Extracting":
                description = f"[green][Extracting {line['id']}]"
            elif status == "Download complete" or status == "Pull complete":
                progress.remove_task(tasks[line["id"]])
                del tasks[line["id"]]
                continue
            else:
                continue

            if line["id"] not in tasks:
                tasks[line["id"]] = progress.add_task(description, total=line["progressDetail"]["total"])
            else:
                progress.update(tasks[line["id"]], completed=line["progressDetail"]["current"])
        print("Downloaded newer image for malsius/whalerecon:latest")


def main():
    client = docker.from_env()
    try:
        client.images.get("malsius/whalerecon")
    except docker.errors.ImageNotFound:
        pretty_pull(client)

    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False, description="Tool used to run AutoRecon in a container and auto generate HTML reports", usage="whalerecon [-h] [-V] [-v] -o <output_path> [autorecon_options]")

    # Used for WhaleRecon
    parser.add_argument("-h", "--help", action="store_true", help="Print help for WhaleRecon and AutoRecon.")
    parser.add_argument("-V", "--version", action="store_true", help="Prints WhaleRecon and AutoRecon version.")  # TODO
    parser.add_argument("-v", "--verbose", action="count", help="Enable verbose output. Repeat for more verbosity.")
    parser.add_argument("-o", "--output", help="The output directory for results.", nargs=1)

    # Arguments with files to be passed in the container
    parser.add_argument("-c", "--config", help=argparse.SUPPRESS, nargs=1)
    parser.add_argument("-g", "--global-file", help=argparse.SUPPRESS, nargs=1)
    parser.add_argument("-t", "--target-file", help=argparse.SUPPRESS, nargs=1)
    parser.add_argument("--plugins-dir", help=argparse.SUPPRESS, nargs=1)
    parser.add_argument("--add-plugins-dir", help=argparse.SUPPRESS, nargs=1)
    parser.add_argument("--dirbuster.wordlist", help=argparse.SUPPRESS, nargs="+")
    parser.add_argument("--global.username-wordlist", help=argparse.SUPPRESS, nargs=1)
    parser.add_argument("--global.password-wordlist", help=argparse.SUPPRESS, nargs=1)

    # Here to be disabled in AutoRecon
    parser.add_argument("--no-port-dirs", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--disable-keyboard-control", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--accessible", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--single-target", action="store_true", help=argparse.SUPPRESS)

    args, unknown_args = parser.parse_known_args()

    if args.help:
        print_help(parser, client)
    elif not args.output:
        parser.error("the following arguments are required: -o/--output")
    else:
        output_path = is_valid_output(args.output[0])
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                tmp_files = os.path.join(tmp_dir, "files")
                os.mkdir(tmp_files)
                tmp_results = os.path.join(tmp_dir, "results")
                os.mkdir(tmp_results)
                tmp_reports = os.path.join(tmp_dir, "reports")
                os.mkdir(tmp_reports)

                autorecon_options = parse_autorecon_input_files(args, tmp_files)
                autorecon_options.extend(unknown_args)
                if args.verbose:
                    autorecon_options.append(f"-{'v' * args.verbose}")

                autorecon_cmd = get_autorecon_cmd(autorecon_options)

                mount_files = docker.types.Mount("/opt/whalerecon/files", tmp_files, type="bind")
                mount_results = docker.types.Mount("/opt/whalerecon/results", tmp_results, type="bind")
                mount_reports = docker.types.Mount("/opt/whalerecon/reports", tmp_reports, type="bind")

                container = client.containers.run(
                    name="whalerecon",
                    mounts=[mount_files, mount_results, mount_reports],
                    network_mode="host",
                    working_dir="/opt/whalerecon",
                    detach=True,
                    image="malsius/whalerecon",
                    command="bash",
                    tty=True
                )

                print(autorecon_cmd)
                run_command(container, autorecon_cmd)

                autorecon_reporting_cmd = "autorecon-reporting results reports"
                print(autorecon_reporting_cmd)
                run_command(container, autorecon_reporting_cmd)

                chown_cmd = f"chown -R {os.getuid()}:{os.getgid()} ."
                print(chown_cmd)
                run_command(container, chown_cmd)

                copy_output(output_path, tmp_results, tmp_reports)

                container.kill()
                container.remove()
            except KeyboardInterrupt:
                print("\nAbort scan")
                chown_cmd = f"chown -R {os.getuid()}:{os.getgid()} ."
                run_command(container, chown_cmd)
                container.kill()
                container.remove()
                exit(1)


if __name__ == '__main__':
    main()
