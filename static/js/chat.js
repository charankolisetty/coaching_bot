$(document).ready(function () {
    const chatMessages = $('#chat-messages');
    const chatForm = $('#chat-form');
    const promptInput = $('#prompt');
    const submitButton = chatForm.find('button[type="submit"]');
    const originalButtonText = submitButton.html();

    // Add initial welcome message if chat is empty
    if (chatMessages.children().length === 0) {
        addMessage("Welcome! How can I assist you today?", 'bot');
    }

    // Auto-resize textarea with max height
    promptInput.on('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        if (this.value === '') {
            this.style.height = '44px';
        }
    });

    // Improved scroll to bottom with smooth behavior
    function scrollToBottom(animate = true) {
        const scrollHeight = chatMessages[0].scrollHeight;
        if (animate) {
            chatMessages.animate({
                scrollTop: scrollHeight
            }, {
                duration: 300,
                easing: 'swing',
                complete: () => {
                    // Double-check scroll position after animation
                    if (chatMessages.scrollTop() + chatMessages.innerHeight() < scrollHeight) {
                        chatMessages.scrollTop(scrollHeight);
                    }
                }
            });
        } else {
            chatMessages.scrollTop(scrollHeight);
        }
    }

    // Initial scroll
    scrollToBottom(false);

    chatForm.on('submit', function (e) {
        e.preventDefault();

        const prompt = promptInput.val().trim();
        if (!prompt) return;

        // Reset textarea height
        promptInput.css('height', '44px');

        // Disable form and show loading state
        chatForm.addClass('disabled');
        submitButton.html('<i class="fas fa-spinner fa-spin mr-2"></i>Sending...');
        submitButton.prop('disabled', true);
        promptInput.prop('disabled', true);

        // Add user message with animation
        addMessage(prompt, 'user');
        promptInput.val('');

        // Show typing indicator with animation
        showTypingIndicator();

        // Send request to server
        $.ajax({
            url: '/chat',
            method: 'POST',
            data: { prompt: prompt },
            success: function (response) {
                removeTypingIndicator();
                if (response.response) {
                    addMessage(response.response, 'bot');
                } else {
                    addMessage("I apologize, but I couldn't process your request. Please try again.", 'bot error');
                }
            },
            error: function (xhr) {
                removeTypingIndicator();
                const errorMessage = xhr.responseJSON?.error || 'An error occurred. Please try again.';
                addMessage(errorMessage, 'bot error');
            },
            complete: function () {
                chatForm.removeClass('disabled');
                submitButton.html(originalButtonText);
                submitButton.prop('disabled', false);
                promptInput.prop('disabled', false);
                promptInput.focus();
                scrollToBottom();
            }
        });
    });

    function addMessage(text, type) {
        const messageHTML = `
            <div class="message-group animate-fade-in">
                <div class="message ${type}-message">
                    <p>${text}</p>
                </div>
            </div>
        `;
        chatMessages.append(messageHTML);
        scrollToBottom();
    }

    function showTypingIndicator() {
        const indicator = `
            <div class="typing-indicator animate-fade-in">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;
        chatMessages.append(indicator);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        $('.typing-indicator').fadeOut(200, function () {
            $(this).remove();
        });
    }

    // Enhanced enter key handling
    promptInput.on('keydown', function (e) {
        if (e.which === 13 && !e.shiftKey) {
            e.preventDefault();
            if (!submitButton.prop('disabled')) {
                chatForm.submit();
            }
        }
    });

    // Prevent form submission while disabled
    chatForm.on('submit', function (e) {
        if (submitButton.prop('disabled')) {
            e.preventDefault();
        }
    });

    // Add this inside your $(document).ready function
    $('#newSessionBtn').on('click', function () {
        // Create form with existing user details
        const form = $('<form>', {
            'method': 'POST',
            'action': '/'
        });

        // Add hidden fields with current session data
        form.append($('<input>', {
            'type': 'hidden',
            'name': 'username',
            'value': userDetails.username  // You'll need to pass this from Flask
        }));

        form.append($('<input>', {
            'type': 'hidden',
            'name': 'industry',
            'value': userDetails.industry
        }));

        form.append($('<input>', {
            'type': 'hidden',
            'name': 'company',
            'value': userDetails.company
        }));

        // Append form to body and submit
        $('body').append(form);
        form.submit();
    });
});