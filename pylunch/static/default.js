function postJson(url, data) {
    request = {
        type: "POST",
        url: url,
        data: data,
        dataType: 'json'
    };
    return $.ajax(request)
}