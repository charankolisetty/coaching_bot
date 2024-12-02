/* chat.js */
$(document).ready(function() {
    const chatMessages = $('#chat-messages');
    const chatForm = $('#chat-form');
    const promptInput = $('#prompt');
    const submitButton = chatForm.find('button[type="submit"]');
    const originalButtonText = submitButton.html();

    // Auto-resize textarea
    promptInput.on('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        if (this.value === '') {
            this.style.height = '44px';
        }
    });

    // Scroll to bottom function
    function scrollToBottom(animate = true) {
        const scrollHeight = chatMessages[0].scrollHeight;
        if (animate) {
            chatMessages.animate({ scrollTop: scrollHeight }, 300, 'swing');
        } else {
            chatMessages.scrollTop(scrollHeight);
        }
    }

    // Initial scroll
    scrollToBottom(false);

    chatForm.on('submit', function(e) {
        e.preventDefault();
        
        const prompt = promptInput.val().trim();
        if (!prompt) return;

        // Reset textarea height
        promptInput.css('height', '44px');

        // Disable form and show loading state
        chatForm.addClass('pointer-events-none opacity-70');
        submitButton.html('<i class="fas fa-spinner fa-spin mr-2"></i>Processing...');
        submitButton.prop('disabled', true);

        // Add user message
        addMessage(prompt, 'user');
        promptInput.val('');

        // Show typing indicator
        showTypingIndicator();

        // Send request to server
        $.ajax({
            url: '/chat',
            method: 'POST',
            data: { prompt: prompt },
            success: function(response) {
                removeTypingIndicator();
                addMessage(response.response, 'bot');
            },
            error: function(xhr) {
                removeTypingIndicator();
                const errorMessage = xhr.responseJSON?.error || 'An error occurred. Please try again.';
                addMessage(errorMessage, 'bot error');
            },
            complete: function() {
                chatForm.removeClass('pointer-events-none opacity-70');
                submitButton.html(originalButtonText);
                submitButton.prop('disabled', false);
                promptInput.focus();
                scrollToBottom();
            }
        });
    });

    function addMessage(text, type) {
        const messageHTML = `
            <div class="message-group">
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
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;
        chatMessages.append(indicator);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        $('.typing-indicator').remove();
    }

    // Handle enter key
    promptInput.on('keydown', function(e) {
        if (e.which === 13 && !e.shiftKey) {
            e.preventDefault();
            chatForm.submit();
        }
    });
});