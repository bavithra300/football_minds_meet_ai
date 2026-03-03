// Utility to toggle visibility
function showPanel(id) {
    document.getElementById(id).classList.remove('hidden');
}

function hidePanel(id) {
    document.getElementById(id).classList.add('hidden');
}

function resetForm(formPanelId, resultsPanelId) {
    hidePanel(resultsPanelId);
    showPanel(formPanelId);
}

// Display error messages
function showError(msg) {
    const errorBox = document.getElementById('formError');
    if (errorBox) {
        errorBox.textContent = msg;
        errorBox.classList.remove('hidden');
    }
}

// Format numbers for display
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Handle Login
const loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(loginForm);
        const submitBtn = loginForm.querySelector('button[type="submit"]');
        const origText = submitBtn.innerHTML;

        submitBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Authenticating...';
        submitBtn.disabled = true;

        try {
            const res = await fetch('/login', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (data.success) {
                window.location.href = '/dashboard';
            } else {
                const msgBox = document.getElementById('loginMessage');
                msgBox.textContent = data.message;
                msgBox.classList.remove('hidden');
                msgBox.classList.add('message-error');
                submitBtn.innerHTML = origText;
                submitBtn.disabled = false;
            }
        } catch (err) {
            console.error(err);
            submitBtn.innerHTML = origText;
            submitBtn.disabled = false;
        }
    });
}

// Handle Player Recommendation
const playerForm = document.getElementById('playerForm');
if (playerForm) {
    playerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        document.getElementById('formError').classList.add('hidden');
        hidePanel('playerFormPanel');
        showPanel('loadingPanel');

        const formData = new FormData(playerForm);

        try {
            const res = await fetch('/player_recommendation', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            hidePanel('loadingPanel');

            if (data.success) {
                renderPlayers(data.ai_recommendations, 'aiCandidates');

                if (data.local_matches && data.local_matches.length > 0) {
                    renderPlayers(data.local_matches, 'localCandidates', true);
                    showPanel('localMatchesSection');
                } else {
                    hidePanel('localMatchesSection');
                }

                showPanel('resultsPanel');
            } else {
                showError(data.message);
                showPanel('playerFormPanel');
            }
        } catch (err) {
            console.error(err);
            hidePanel('loadingPanel');
            showError("Network error calculating recommendations.");
            showPanel('playerFormPanel');
        }
    });
}

// Render Player Cards
function renderPlayers(players, containerId, isLocal = false) {
    const container = document.getElementById(containerId);
    const template = document.getElementById('candidateCardTemplate');
    container.innerHTML = '';

    if (players.length === 0) {
        container.innerHTML = '<p class="text-muted">No candidates found matching strict criteria.</p>';
        return;
    }

    players.forEach((p, index) => {
        const clone = template.content.cloneNode(true);

        // Headers & Ranks
        clone.querySelector('.rank-num').textContent = index + 1;

        const score = p.scout_score || (isLocal ? 'N/A' : '0');
        clone.querySelector('.score-num').textContent = score;

        if (score !== 'N/A') {
            const offset = 125 - (125 * parseInt(score)) / 100;
            clone.querySelector('.score-circle').style.strokeDashoffset = offset;

            // Color coding based on score
            const circle = clone.querySelector('.score-circle');
            const num = clone.querySelector('.score-num');
            if (score >= 90) { circle.style.stroke = 'var(--gold)'; num.style.color = 'var(--gold)'; }
            else if (score >= 80) { circle.style.stroke = 'var(--success)'; num.style.color = 'var(--success)'; }
            else if (score >= 70) { circle.style.stroke = 'var(--warning)'; num.style.color = 'var(--warning)'; }
            else { circle.style.stroke = 'var(--danger)'; num.style.color = 'var(--danger)'; }
        } else {
            clone.querySelector('.score-circle').style.strokeDashoffset = 125;
        }

        // Profile mapping
        clone.querySelector('.cand-name').textContent = p.name || 'Unknown Player';
        clone.querySelector('.cand-club span').textContent = p.current_club || p.club || 'Free Agent';

        // Deep search for matches played since AI can format it weirdly
        let matches = p.matches_played || (p.stats && p.stats.matches_played) || p.matches || 'N/A';
        clone.querySelector('.cand-matches').textContent = matches;

        let strength = p.key_strength || p.strength || (p.stats && p.stats.key_strength) || 'N/A';
        clone.querySelector('.cand-strength').textContent = strength;

        // Analysis
        const perfP = clone.querySelector('.cand-perf');
        const justP = clone.querySelector('.cand-just');

        if (isLocal) {
            perfP.textContent = `Age: ${p.age} | Exp: ${p.experience} Yrs`;
            justP.textContent = "Registered in local scouting database.";

            // If local, try loading the actual photo
            if (p.profile_photo_path) {
                // Ensure the path uses correct web formatting
                let imgPath = p.profile_photo_path.replace(/\\/g, '/');
                clone.querySelector('.profile-img').src = '/' + imgPath;
            }
        } else {
            perfP.textContent = p.performance_analysis || p.role_performance || 'Analysis pending.';
            justP.textContent = p.coach_justification || 'Fits profile.';

            // For hackathon, scraping Google Images dynamically in frontend is blocked by CORS.
            // We use a high-quality placeholder photo to maintain the premium dashboard feel.
            const placeholders = [
                'https://images.unsplash.com/photo-1543326727-cf6c39b8f84c?w=200&h=200&fit=crop', // Player 1
                'https://images.unsplash.com/photo-1518605368461-1e1e38ce8ba4?w=200&h=200&fit=crop', // Player 2
                'https://images.unsplash.com/photo-1579952363873-27f3bade9f55?w=200&h=200&fit=crop', // Player 3
                'https://images.unsplash.com/photo-1518655048521-f130df041f66?w=200&h=200&fit=crop'  // Player 4
            ];

            // Pick a consistent random placeholder based on the name length
            let nameLen = (p.name || '').length;
            let photoUrl = placeholders[nameLen % placeholders.length];

            clone.querySelector('.profile-img').src = photoUrl;
        }

        container.appendChild(clone);
    });
}

// Handle Coach Recommendation
const coachForm = document.getElementById('coachForm');
if (coachForm) {
    coachForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        document.getElementById('formError').classList.add('hidden');
        hidePanel('coachFormPanel');
        showPanel('loadingPanel');

        const formData = new FormData(coachForm);

        try {
            const res = await fetch('/coach_recommendation', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            hidePanel('loadingPanel');

            if (data.success) {
                renderCoaches(data.ai_recommendations, 'aiCandidates');
                showPanel('resultsPanel');
            } else {
                showError(data.message);
                showPanel('coachFormPanel');
            }
        } catch (err) {
            console.error(err);
            hidePanel('loadingPanel');
            showError("Network error calculating recommendations.");
            showPanel('coachFormPanel');
        }
    });
}

// Render Coach Cards
function renderCoaches(coaches, containerId) {
    const container = document.getElementById(containerId);
    const template = document.getElementById('coachCardTemplate');
    container.innerHTML = '';

    if (coaches.length === 0) {
        container.innerHTML = '<p class="text-muted">No tactical managers found matching criteria.</p>';
        return;
    }

    coaches.forEach((c, index) => {
        const clone = template.content.cloneNode(true);

        clone.querySelector('.rank-num').textContent = index + 1;

        const score = c.scout_score || 0;
        clone.querySelector('.score-num').textContent = score;
        const offset = 125 - (125 * parseInt(score)) / 100;
        clone.querySelector('.score-circle').style.strokeDashoffset = offset;

        clone.querySelector('.cand-name').textContent = c.name;
        clone.querySelector('.cand-club span').textContent = c.current_club || 'Unattached';
        clone.querySelector('.cand-exp').textContent = c.experience || c.experience_years || 'N/A';
        clone.querySelector('.cand-salary').textContent = c.estimated_salary || 'N/A';

        // Analysis
        clone.querySelector('.cand-perf').textContent = c.tactical_analysis || `Preferred Formation: ${c.preferred_formation || 'Flexible'}`;
        clone.querySelector('.cand-just').textContent = c.justification || c.key_strength || 'Strong tactical fit.';

        // Image
        // Use a generic coach/manager looking photo
        const coachPlaceholders = [
            'https://images.unsplash.com/photo-1580828369019-22204c405901?w=200&h=200&fit=crop',
            'https://images.unsplash.com/photo-1558507652-2d9626c4e67a?w=200&h=200&fit=crop',
            'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=200&h=200&fit=crop'
        ];
        let nameLen = (c.name || '').length;
        clone.querySelector('.profile-img').src = coachPlaceholders[nameLen % coachPlaceholders.length];

        container.appendChild(clone);
    });
}

// Handle New Player Registration
const registerForm = document.getElementById('registerForm');
if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        document.getElementById('formError').classList.add('hidden');
        hidePanel('registerFormPanel');
        showPanel('loadingPanel');

        const formData = new FormData(registerForm);

        try {
            const res = await fetch('/new_player', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            hidePanel('loadingPanel');

            if (data.success) {
                showPanel('resultsPanel');
            } else {
                showError(data.message);
                showPanel('registerFormPanel');
            }
        } catch (err) {
            console.error(err);
            hidePanel('loadingPanel');
            showError("Network error during registration.");
            showPanel('registerFormPanel');
        }
    });

    // File input UX
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', (e) => {
            const wrapper = e.target.parentElement;
            const span = wrapper.querySelector('span');
            if (e.target.files.length > 0) {
                span.textContent = e.target.files[0].name;
                span.style.color = 'var(--primary)';
                wrapper.style.borderColor = 'var(--primary)';
            }
        });
    });
}
