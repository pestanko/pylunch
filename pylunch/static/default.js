function postJson(url, data) {
    request = {
        type: "POST",
        url: url,
        data: data,
        dataType: 'json'
    };
    return $.ajax(request)
}


function getJson(url) {
    request = {
        type: "GET",
        url: url,
        dataType: 'json'
    };
    return $.ajax(request)
}