"""UnDocker object to parse the unRAID Docker XML template file."""

import argparse
import os
import xml.etree.ElementTree as ET
import textwrap

import yaml

__author__ = "Arif Er"
__copyright__ = "Copyright 2022, Arif Er"
__license__ = "GNU General Public License Version 3 (GPL-3.0)"
__version__ = "0.1.0"
__status__ = "Prototype"


class UnDocker:
    """The unRAID docker template."""

    compose_version = "3.7"  # Following this compose file format

    def __init__(self, template: str, compose: str = "", config_labels: bool = False):
        """Initialise the docker template for parsing.

        .. Keyword Arguments:
        :param template: Path to the template file.
        :param compose: Path to the compose file. (default "")
        :params config: Write unRAID DockerMan configuration attributes and
        values as labels if True. (default False)
        """
        self.tree = ET.parse(template)
        if compose:
            self.yaml = compose
        else:
            self.yaml = os.path.join(os.path.dirname(compose), "docker-compose.yaml")
        self.config_labels = config_labels

    def _tag(self, tag: str) -> str:
        """Extract out XML tag text.

        .. Keyword Arguments:
        :param tag: Name of the XML tag.

        .. Returns:
        :return: The tag's text, if any.
        """
        if self.tree.find(tag).text:
            return str(self.tree.find(tag).text)
        return ""

    def _unraid_labels(self) -> dict:
        """Set extra details from template as net.unraid.template labels.

        .. Returns:
        :return: The container's template information as a dictionary.
        """
        return {
            "net.unraid.docker.registry": self._tag("Registry"),
            "net.unraid.docker.shell": self._tag("Shell"),
            "net.unraid.docker.support": self._tag("Support"),
            "net.unraid.docker.project": self._tag("Project"),
            "net.unraid.docker.overview": self._tag("Overview"),
            "net.unraid.docker.category": self._tag("Category"),
            "net.unraid.docker.icon": self._tag("Icon"),
            "net.unraid.docker.webui": self._tag("WebUI"),
            "net.unraid.docker.managed": "compose",
            "net.unraid.docker.template": self._tag("TemplateURL"),
            "net.unraid.docker.installed": self._tag("DateInstalled"),
            "net.unraid.docker.donate.text": self._tag("DonateText"),
            "net.unraid.docker.donate.link": self._tag("DonateLink"),
            "net.unraid.docker.requires": self._tag("Requires"),
        }

    def _unraid_environment(self) -> dict:
        """Set extra environments for unRAID system.

        .. Returns:
        :return: The default unRAID environment as a dictionary.
        """
        return {
            "TZ": "UTC",  # FIXME not a proper way of getting TZ
            "HOST_OS": "Unraid",
            "HOST_HOSTNAME": self._tag("Name"),
            "HOST_CONTAINERNAME": self._tag("Name"),
        }

    @staticmethod
    def _extra_params(params: str) -> dict:
        """Parse the ExtraParams tag.

        TODO The maps here are not exhaustive.

        .. Keyword Arguments:
        :param params: String from the ExtraParams tag of the template.

        .. Returns:
        :return: Extra Docker Compose configuration as a dictionary.
        """
        docker_parser = argparse.ArgumentParser()
        known_args = [
            (["--restart"], "restart"),
            (["--net", "--network"], "networks")
        ]
        _ = [docker_parser.add_argument(i[0], dest=i[1]) for i in known_args]
        docker_args = docker_parser.parse_known_args(params.split())[0]
        extra_params = {}
        for attr in docker_args._get_kwargs():
            if attr[1]:
                extra_params[args.__getattribute__(attr[0])] = attr[1]
        return extra_params

    def _configs(self) -> tuple:
        """Parse the Config tags.

        :return: Ports, mount volumes, devices, environment, and labels as
        specified in the template file.
        """
        ports = []
        volumes = []
        devices = []
        environment = {}
        labels = {}

        for config in self.tree.findall("Config"):
            get = config.attrib.get
            header = f"net.unraid.docker.config.{get('Name').replace(' ', '_')}"

            # '$' characters need to be escaped
            if config.text:
                value = config.text.replace("$", "$$")
            else:
                value = get("Default").replace("$", "$$")

            # Populate the right target from reading the config Type.
            if get("Type") == "Port":
                ports.append(
                    {
                        "target": int(get("Target")),
                        "published": int(value),
                        "protocol": get("Mode") if get("Mode") else "",
                    }
                )

            if get("Type") == "Path":
                volumes.append(
                    f"{value}:{get('Target')}"
                    + (f":{get('Mode')}" if get("Mode") else "")
                )

            if get("Type") == "Devices":
                devices.append(
                    f"{value}:{get('Target')}"
                    + (f":{get('Mode')}" if get("Mode") else "")
                )

            if get("Type") == "Variable":
                environment[get("Target")] = str(value)

            if get("Type") == "Label":
                labels[get("Target")] = value

            # Fill in the excess information as new unRAID labels and default
            # unRAID environment.
            if self.config_labels:
                labels.update(
                    {
                        f"{header}.default": get("Default"),
                        f"{header}.description": get("Description"),
                        f"{header}.display": get("Display"),
                        f"{header}.required": get("Required"),
                        f"{header}.mask": get("Mask"),
                    }
                )
        return ports, volumes, environment, labels, devices

    def networks(self) -> dict:
        """Parse the template to set up external network.

        .. Returns:
        :return: The external network as a dictionary.
        """
        return {
            self._tag("Network"): {
                "external": True,
                "name": self._tag("Network")
            }
        }

    def services(self) -> dict:
        """Parse the template to declare the service.

        .. Returns:
        :return: The services as a dictionary.
        """
        ports, volumes, environment, labels, devices = self._configs()
        labels.update(self._unraid_labels())
        environment.update(self._unraid_environment())
        return {
            self._tag("Name"): {
                "container_name": self._tag("Name"),
                "image": self._tag("Repository"),
                "privileged": not bool(self._tag("Privileged") == "false"),
                "ports": ports,
                "volumes": volumes,
                "environment": environment,
                "labels": labels,
                "devices": devices,
                "networks": [self._tag("Network")],
                "cpuset": self._tag("CPUset"),
                "command": self._tag("PostArgs"),  # FIXME check if correct
            }
        }

    def compose(self) -> None:
        """Write the data into the target docker compose file."""
        with open(self.yaml, "w", encoding="utf-8") as comp:
            yaml.safe_dump(
                {
                    "version": self.compose_version,
                    "services": self.services(),
                    "networks": self.networks(),
                },
                comp,
                sort_keys=False,
            )


def argparser() -> tuple:
    """Set up the argument parser

    :return: The parsed known and unknown arguments
    """
    parser = argparse.ArgumentParser(
        description=textwrap.dedent(
            f"""\
        undock-compose v{__version__} - [{__status__}]
        {__copyright__}
        Convert your unRAID Docker XML templates to Docker Compose YAML files.
        """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        nargs=1,
        help=textwrap.dedent("""\
        Path to the input XML template file.
        """),
    )
    parser.add_argument(
        "output",
        nargs="?",
        help=textwrap.dedent(
            """\
        Path to the output YAML file. Defaults to 'docker-compose.yaml' in the
        same directory as the input.
        """
        ),
        default="",
    )
    parser.add_argument(
        "--labels",
        "-l",
        action="store_true",
        help="Flag to include unRAID Docker labels for configurations",
    )
    return parser.parse_known_args()
