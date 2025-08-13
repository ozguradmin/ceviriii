$(document).ready(function() {
    function getApiBase() {
        return (window.API_BASE || localStorage.getItem('apiBase') || '').replace(/\/$/, '');
    }
    function api(path) {
        const base = getApiBase();
        if (!path.startsWith('/')) path = '/' + path;
        return base + path;
    }
    // Hazır font listesini çek ve doldur
    function loadAvailableFonts() {
        $.get(api('/api/fonts'), function(resp) {
            if (!resp || !resp.fonts) return;
            const select = $('#font-select');
            select.empty();
            select.append('<option value="">(Seçilmedi)</option>');
            resp.fonts.forEach(function(item) {
                const label = item.family ? (item.family + ' (' + item.file + ')') : item.file;
                const opt = $('<option>').val(item.file).text(label);
                select.append(opt);
            });
        });
    }
    loadAvailableFonts();

    // Yerel IP bilgisini getir ve mobil erişim ipucuna yaz
    function loadHostInfo() {
        $.get(api('/api/host'), function(resp) {
            if (!resp) return;
            const ip = resp.ip || '127.0.0.1';
            const port = resp.port || 5001;
            $('#mobile-hint').text(`Aynı Wi‑Fi'da mobil cihazdan bağlanmak için: http://${ip}:${port}`);
        });
    }
    loadHostInfo();
    $('#upload-form').on('submit', function(event) {
        event.preventDefault();

        // FormData kullanarak hem video hem de stil ayarlarını gönder
        var formData = new FormData(this);
        var fileInput = $('#video-file')[0];

        if (fileInput.files.length === 0) {
            alert("Lütfen bir video dosyası seçin.");
            return;
        }
        
        // İlk işlemde de stil ayarlarını ekle
        formData.append('has_background', $('#background-switch').is(':checked'));
        formData.append('has_animation', $('#animation-switch').is(':checked'));
        formData.append('is_bold', $('#bold-switch').is(':checked'));
        formData.append('timing_relax', $('#timing-relax-switch').is(':checked'));
        formData.append('bg_opacity', $('#bg-opacity').val());
        formData.append('margin_v', $('#margin-v').val());
        // Yeni gelişmiş stil parametreleri
        formData.append('font_size', $('#font-size').val() || 60);
        formData.append('outline_px', $('#outline-px').val() || 3);
        formData.append('shadow_px', $('#shadow-px').val() || 2);
        formData.append('resolution', $('#resolution').val() || '1080x1920');
        formData.append('alignment', $('#alignment').val() || 2);
        formData.append('crf', $('#crf').val() || 20);
        formData.append('fps', $('#fps').val() || '');
        formData.append('margin_l', $('#margin-l').val() || 80);
        formData.append('margin_r', $('#margin-r').val() || 80);
        // Hazır font seçimi
        formData.append('selected_font', $('#font-select').val());

        // Font dosyası varsa onu da ekle (ilk işlemde varsayılan kullanılacak)
        const fontFile = $('#font-file')[0].files[0];
         if (fontFile) {
            formData.append('font_file', fontFile);
        }

        var videoURL = URL.createObjectURL(fileInput.files[0]);
        $('#video-preview').attr('src', videoURL);

        $('#submit-btn').prop('disabled', true).text('İşlem Başlatılıyor...');
        $('#status-message').text('Video sunucuya yükleniyor...');
        $('.progress').show();
        $('#progress-bar').css('width', '5%').text('Yükleniyor...');
        $('#download-link').hide();
        $('#editor-container').hide();

        $.ajax({
            url: api('/process'),
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function(response) {
                if (response.success && response.task_id) {
                    // Görev ID'si alındı, durumu kontrol etmeye başla
                    checkStatus(response.task_id);
                } else {
                    handleError(response.error || "Sunucudan geçersiz yanıt alındı.");
                }
            },
            error: function(xhr, status, error) {
                 handleError("Sunucuyla iletişim kurulamadı: " + error);
                 $('#submit-btn').prop('disabled', false).text('Altyazı Oluşturmaya Başla');
                 $('.progress').hide();
            }
        });
    });

    let originalSubtitles = []; // Orijinal altyazıları saklamak için
    let currentVideoPath = ""; // İşlenmiş video yolunu saklamak için

    function checkStatus(taskId) {
        var interval = setInterval(function() {
            $.ajax({
                url: api('/status/' + taskId),
                type: 'GET',
                success: function(response) {
                    // İlerleme çubuğunu ve mesajı güncelle
                    $('#status-message').text(response.message || '');
                    if(response.progress) {
                        $('#progress-bar').css('width', response.progress + '%').text(response.progress + '%');
                    }

                    if (response.status === 'complete') {
                        clearInterval(interval); // Sorgulamayı durdur
                        $('#status-message').text('İşlem başarıyla tamamlandı!');
                        currentVideoPath = response.video_path; // Video yolunu sakla
                        
                        // Önbelleği atlatmak için URL'ye rastgele bir parametre ekle
                        const finalUrl = api('/' + currentVideoPath) + '?t=' + new Date().getTime();
                        $('#video-preview').attr('src', finalUrl);
                        const fname = currentVideoPath.split('/').pop();
                        const dlUrl = api('/download/' + fname) + '?t=' + new Date().getTime();
                        $('#download-link').attr('href', dlUrl).attr('download','video.mp4').show();

                        if(response.subtitles && response.subtitles.length > 0) {
                            originalSubtitles = JSON.parse(JSON.stringify(response.subtitles)); // Derin kopya
                            populateSubtitlesTable(originalSubtitles);
                            populateColorPalette(originalSubtitles); // Renk paletini oluştur
                            $('#editor-container').show();
                        }
                        $('#submit-btn').prop('disabled', false).text('Yeni Video İşle');

                    } else if (response.status === 'error') {
                        clearInterval(interval); // Sorgulamayı durdur
                        handleError(response.message || 'Bilinmeyen bir hata oluştu.');
                        $('#submit-btn').prop('disabled', false).text('Tekrar Dene');
                    }
                },
                error: function() {
                    clearInterval(interval); // Sorgulamayı durdur
                    handleError("Görev durumu kontrol edilirken sunucuyla iletişim kesildi.");
                    $('#submit-btn').prop('disabled', false).text('Tekrar Dene');
                }
            });
        }, 2000); // Her 2 saniyede bir durumu kontrol et
    }

    function populateSubtitlesTable(subtitles) {
        var tableBody = $('#subtitles-table');
        tableBody.empty(); // Önceki verileri temizle

        subtitles.forEach(function(sub, index) {
            var row = `
                <tr data-id="${index}">
                    <td><input type="text" class="form-control" value="${sub.start.toFixed(2)}"></td>
                    <td><input type="text" class="form-control" value="${sub.end.toFixed(2)}"></td>
                    <td><input type="text" class="form-control" value="${sub.speaker}"></td>
                    <td><textarea class="form-control">${sub.text}</textarea></td>
                    <td><button class="btn btn-danger btn-sm delete-sub-btn">Sil</button></td>
                </tr>
            `;
            tableBody.append(row);
        });
    }

    function populateColorPalette(subtitles) {
        const palette = $('#color-palette');
        palette.empty();
        const speakers = [...new Set(subtitles.map(s => s.speaker))]; // Benzersiz konuşmacıları bul
        
        const defaultColors = ['#FFFF00', '#FFFFFF', '#00FFFF', '#00FF00', '#FF00FF'];

        speakers.forEach((speaker, index) => {
            const color = defaultColors[index % defaultColors.length];
            const colorPickerHTML = `
                <div class="d-flex align-items-center">
                    <label for="color-${index}" class="form-label me-2 mb-0">${speaker}:</label>
                    <input type="color" class="form-control form-control-color" id="color-${speaker.replace(/ /g, '')}" value="${color}" data-speaker="${speaker}">
                </div>
            `;
            palette.append(colorPickerHTML);
        });
    }

    function handleError(errorMessage) {
        $('#status-message').html(`<div class="alert alert-danger">${errorMessage}</div>`);
        $('#progress-bar').addClass('bg-danger').css('width', '100%').text('Hata!');
    }

    function getSubtitlesFromTable() {
        const subtitles = [];
        $('#subtitles-table tr').each(function() {
            const row = $(this);
            subtitles.push({
                start: parseFloat(row.find('td:eq(0) input').val()),
                end: parseFloat(row.find('td:eq(1) input').val()),
                speaker: row.find('td:eq(2) input').val(),
                text: row.find('td:eq(3) textarea').val()
            });
        });
        return subtitles;
    }

    // Dışa aktarma (SRT ve ASS)
    function secondsToSrtTime(sec) {
        const s = Math.max(0, Number(sec) || 0);
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        const ss = Math.floor(s % 60);
        const ms = Math.floor((s - Math.floor(s)) * 1000);
        const pad = (n, w) => String(n).padStart(w, '0');
        return `${pad(h,2)}:${pad(m,2)}:${pad(ss,2)},${pad(ms,3)}`;
    }
    function exportSRT(subs) {
        let idx = 1;
        let lines = [];
        subs.forEach(s => {
            lines.push(String(idx++));
            lines.push(`${secondsToSrtTime(s.start)} --> ${secondsToSrtTime(s.end)}`);
            lines.push((s.text || '').replace(/\r?\n/g, '\n'));
            lines.push('');
        });
        const blob = new Blob([lines.join('\r\n')], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'subtitles.srt'; a.click();
        URL.revokeObjectURL(url);
    }
    function exportASS(subs) {
        const header = `[Script Info]\nTitle: Exported\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,60,&H00FFFF,&HFFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,2,2,10,10,450,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n`;
        function toAssTime(sec) {
            const s = Math.max(0, Number(sec) || 0);
            const h = Math.floor(s / 3600);
            const m = Math.floor((s % 3600) / 60);
            const ss = Math.floor(s % 60);
            const cs = Math.floor((s - Math.floor(s)) * 100); // centiseconds
            const pad = (n, w) => String(n).padStart(w, '0');
            return `${h}:${pad(m,2)}:${pad(ss,2)}.${pad(cs,2)}`;
        }
        let events = '';
        subs.forEach(s => {
            const text = (s.text || '').replace(/\n/g, '\\N');
            events += `Dialogue: 0,${toAssTime(s.start)},${toAssTime(s.end)},Default,,0,0,0,,${text}\n`;
        });
        const blob = new Blob([header + events], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'subtitles.ass'; a.click();
        URL.revokeObjectURL(url);
    }

    function getColorMap() {
        const colorMap = {};
        $('#color-palette input[type="color"]').each(function() {
            const speaker = $(this).data('speaker');
            let hexColor = $(this).val(); // #RRGGBB
            // HEX'i ASS formatına (AABBGGRR) çevir
            let assColor = '&H00' + hexColor.substring(5, 7) + hexColor.substring(3, 5) + hexColor.substring(1, 3).toUpperCase();
            colorMap[speaker] = assColor;
        });
        return colorMap;
    }


    // Manuel metin ekleme
    $('#add-text-btn').on('click', function() {
        const tableBody = $('#subtitles-table');
        const newIndex = tableBody.find('tr').length;
        const row = `
            <tr data-id="${newIndex}">
                <td><input type="text" class="form-control" value="0.00"></td>
                <td><input type="text" class="form-control" value="0.00"></td>
                <td><input type="text" class="form-control" value="Manuel Metin"></td>
                <td><textarea class="form-control"></textarea></td>
                <td><button class="btn btn-danger btn-sm delete-sub-btn">Sil</button></td>
            </tr>
        `;
        tableBody.append(row);
    });

    // Arka plan anahtarı değiştiğinde opaklık kaydırıcısını göster/gizle
    $('#background-switch').on('change', function() {
        if ($(this).is(':checked')) {
            $('#opacity-control').show();
        } else {
            $('#opacity-control').hide();
        }
    });

    // Değişiklikleri uygula butonu
    $('#apply-changes-btn').on('click', function() {
        const editedSubtitles = getSubtitlesFromTable();
        const colorMap = getColorMap();
        const fontFile = $('#font-file')[0].files[0];
        
        // FormData kullanarak hem JSON hem de dosyayı gönder
        const formData = new FormData();
        formData.append('video_path', currentVideoPath);
        formData.append('subtitles', JSON.stringify(editedSubtitles));
        formData.append('color_map', JSON.stringify(colorMap));
        formData.append('has_background', $('#background-switch').is(':checked'));
        formData.append('has_animation', $('#animation-switch').is(':checked'));
        formData.append('is_bold', $('#bold-switch').is(':checked'));
        formData.append('timing_relax', $('#timing-relax-switch').is(':checked'));
        formData.append('bg_opacity', $('#bg-opacity').val());
        formData.append('margin_v', $('#margin-v').val()); // Dikey konumu ekle
        formData.append('font_size', $('#font-size').val() || 60);
        formData.append('outline_px', $('#outline-px').val() || 3);
        formData.append('shadow_px', $('#shadow-px').val() || 2);
        formData.append('alignment', $('#alignment').val() || 2);
        formData.append('crf', $('#crf').val() || 20);
        formData.append('fps', $('#fps').val() || '');
        formData.append('margin_l', $('#margin-l').val() || 80);
        formData.append('margin_r', $('#margin-r').val() || 80);
        formData.append('selected_font', $('#font-select').val());
        
        if (fontFile) {
            formData.append('font_file', fontFile);
        }

        $(this).prop('disabled', true).text('Uygulanıyor...');

        $.ajax({
            url: api('/reprocess'),
            type: 'POST',
            data: formData,
            processData: false, // FormData için zorunlu
            contentType: false, // FormData için zorunlu
            success: function(response) {
                if (response.success && response.task_id) {
                    checkStatus(response.task_id);
                } else {
                    handleError(response.error || 'Yeniden işleme başlatılamadı.');
                }
            },
            error: function() {
                handleError('Yeniden işleme sırasında sunucu hatası.');
            },
            complete: function() {
                $('#apply-changes-btn').prop('disabled', false).text('Değişiklikleri Uygula ve Videoyu Yeniden Oluştur');
            }
        });
    });

    $('#export-srt-btn').on('click', function() {
        const subs = getSubtitlesFromTable();
        exportSRT(subs);
    });
    $('#export-ass-btn').on('click', function() {
        const subs = getSubtitlesFromTable();
        exportASS(subs);
    });

    // Mobil alt bar kısayolları
    $('#action-upload').on('click', function(){ $('#video-file').trigger('click'); });
    $('#action-apply').on('click', function(){ $('#apply-changes-btn').trigger('click'); });
    $('#action-download').on('click', function(){
        const href = $('#download-link').attr('href');
        if(!href) return;
        const a = document.createElement('a');
        a.href = href; a.download = 'video.mp4'; document.body.appendChild(a); a.click(); a.remove();
    });

    // Satır silme butonu (henüz backend'i yok)
     $('#subtitles-table').on('click', '.delete-sub-btn', function() {
        $(this).closest('tr').remove();
    });

    // Dikey konum kaydırıcısı için canlı önizleme
    $('#margin-v').on('input', function() {
        const marginValue = $(this).val();
        $('#margin-v-value').text(marginValue);
        
        // Canlı önizleme
        const previewContainer = $('#live-preview-container');
        const previewText = $('#live-preview-text');
        previewContainer.show();
        
        // Kaydırıcı değeri (50-1500) ile CSS `bottom` değeri (0-90px) arasında orantı kur
        const bottomPosition = ((marginValue - 50) / (1500 - 50)) * 85; // 100px'lik kutuda ~90px'e kadar
        previewText.css('bottom', bottomPosition + 'px');
    });

});
