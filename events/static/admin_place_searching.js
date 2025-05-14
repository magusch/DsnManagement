window.addEventListener('load', function () {
    var $ = window.django && window.django.jQuery;
    if (!$) {
        console.error('django.jQuery is not available yet');
        return;
    } else {
    }

    $(function () {
        let debounceTimeout;
            $('.place-autocomplete').on('input', function () {
                var query = $(this).val();
                clearTimeout(debounceTimeout);
                debounceTimeout = setTimeout(function () {
                    if (query.length >= 2) {
                        var resultsDiv = $('#place-autocomplete-results');
                        resultsDiv.html('<div class="place-searching">Идёт поиск</div>')
                        $.get('/place/place-autocomplete/', {query: query}, function (data) {
                            resultsDiv.empty();
                            if (data.results.length > 0) {
                                data.results.forEach(function (result) {
                                    resultsDiv.append('<div><a href="#" class="place-found" data-id="' + result.id + '">' + result.place_name + '</a></div>');
                                });
                            } else {
                                resultsDiv.append('<div class="no-results">Ничего не найдено</div>');
                            }
                        });
                    };
                }, 600);
            });

            $('#place-autocomplete-results').on('click', 'a', function (e) {
                e.preventDefault();
                var placeId = $(this).data('id');
                var placeName = $(this).text();
                $('.place-autocomplete').val(placeName);
                $('#id_place').val(placeId);
            });

    });
});
