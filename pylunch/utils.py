import logging

log = logging.getLogger(__name__)


def write_instances(instances, transform=None, writer=None):
    writer = writer or print
    log.debug(f"Printing: {instances}")
    if instances is None or not instances:
        writer("**No instance has been found**")

    elif isinstance(instances, list):
        for instance in instances:
            if instance is not None:
                log.info(f"Sending one response from list: {instances}")
                writer(transform(instance))
    else:
        log.info(f"Sending one response: {instances}")
        writer(transform(instances))