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

def generate_nice_header(*strings):
    def _for_print(max_l, curr, char='='):
        return char * (max_l - curr)

    def _print_text(max_l, text):
        buffer = ''
        buffer += f"\n===  {text}"
        buffer +=_for_print(max_l, len(text), char=' ') 
        buffer += "  ==="
        return buffer

    def _beg_end_line(max_l):
        return f"\n{_for_print(max_l + 10, 0)}"
    
    max_len = max(len(text) for text in strings)

    result = _beg_end_line(max_len)
    for text in strings:
        result += _print_text(max_len, text)
    result += _beg_end_line(max_len)
    return result + "\n\n"
