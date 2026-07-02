from typing import Final, TypeAlias

GraphQLProviderConfig: TypeAlias = dict[str, str]

GRAPHQL_PROVIDER_ID: Final[str] = "graphql"


def createGraphQLProvider(config: GraphQLProviderConfig) -> object:
    return config

