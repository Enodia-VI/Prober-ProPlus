from abc import ABC, abstractmethod
from ipaddress import IPv4Address, IPv6Address
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# Richieste API - esecuzione suite legacy
class RunSuiteRequest(BaseModel):
    suite: str
    dns4_server: str
    dns6_server: Optional[str] = None



# Modelli per gestire l'output dei Plugin
class PluginError(BaseModel):
    code: str
    message: str


class PluginOutput(BaseModel):
    ok: bool
    data: Optional[Any] = None
    error: Optional[PluginError] = None


# Modello utilizzato per i test
class AssertionModel(BaseModel):
    op: Literal[
        "equals",
        "contains",
        "not_contains",
    ]
    value: Any


class AssertionGroup(BaseModel):
    """
    Riflette il formato realmente usato in config.yml e da
    Evaluator.evaluate(): un dict con chiavi opzionali "all"/"any",
    non una lista piatta di assertion.
    """

    all: Optional[list[AssertionModel]] = None
    any: Optional[list[AssertionModel]] = None

    @model_validator(mode="after")
    def validate_at_least_one_group(self):
        if self.all is None and self.any is None:
            raise ValueError(
                "AssertionGroup deve contenere almeno una tra "
                "'all' e 'any'"
            )

        return self


class DnsInput(BaseModel):
    qname: str
    qtype: str


class NicUpdateInput(BaseModel):
    hostname: str
    username: str
    password: str
    url: str


class TestCase(BaseModel):
    id: str
    name: str
    type: Literal[
        "dns_query",
        "nic_update",
        "dot",
        "doh",
    ]
    input: Union[DnsInput, NicUpdateInput]
    assertions: AssertionGroup
    critical: bool = False


# Interfaccia Base astratta dei Plugin

class BasePlugin(ABC):

    @abstractmethod
    async def run(
        self,
        input_data: Union[DnsInput, NicUpdateInput],
        resolver: str,
    ) -> PluginOutput:
        raise NotImplementedError



# Modelli per la lista dei nodi DNS
# (Ansible usage)
class DnsServerEntry(BaseModel):
    name: str
    ip: str
    ipv6: Optional[str] = None
    continent: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    cluster: Optional[str] = None


class PushDnsServersRequest(BaseModel):
    servers: list[DnsServerEntry]


# Target di test ricevuto dalla macchina Ansible

class TestTarget(BaseModel):
    hostname: str = Field(
        min_length=1,
    )

    node_id: int = Field(
        ge=1,
    )

    ipv4: IPv4Address | None = None

    ipv6: IPv6Address | None = None

    continent: str = Field(
        min_length=1,
    )

    country: str = Field(
        min_length=1,
    )

    city: str = Field(
        min_length=1,
    )

    site: str = Field(
        min_length=1,
    )

    cluster_id: int = Field(
        ge=1,
    )

    cluster_name: str = Field(
        min_length=1,
    )

    carrier: str = Field(
        min_length=1,
    )

    device_type: str = Field(
        min_length=1,
    )

    active: bool

    @model_validator(mode="after")
    def validate_addresses(self):
        if self.ipv4 is None and self.ipv6 is None:
            raise ValueError(
                "Target must have at least one of ipv4 or ipv6"
            )

        return self



# Richiesta di creazione di un nuovo test job

class TestRunRequest(BaseModel):
    targets: list[TestTarget] = Field(
        min_length=1,
    )

    suites: list[
        Literal[
            "from_ipv4",
            "from_ipv6",
        ]
    ] = Field(
        min_length=1,
    )

    requested_by: str = Field(
        default="ansible",
        min_length=1,
        max_length=100,
    )

    send_email: bool = False

    @field_validator("suites")
    @classmethod
    def validate_suites(cls, value):
        if len(value) != len(set(value)):
            raise ValueError(
                "Duplicate suites are not allowed"
            )

        return value



# Risposta per la creazione del job
class TestRunAccepted(BaseModel):
    job_id: str

    status: Literal[
        "queued",
        "running",
    ]