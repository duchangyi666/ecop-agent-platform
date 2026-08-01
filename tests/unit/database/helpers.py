from sqlalchemy import Constraint, MetaData


def find_constraint(table_name: str, constraint_name: str, metadata: MetaData) -> Constraint | None:
    table = metadata.tables.get(table_name)
    if table is None:
        return None

    for constraint in table.constraints:
        if constraint.name == constraint_name:
            return constraint

    return None
