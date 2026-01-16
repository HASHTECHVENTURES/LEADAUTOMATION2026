// Load projects IMMEDIATELY when script loads (don't wait for DOMContentLoaded)
(function() {
    function loadProjects() {
        const dropdown = document.getElementById('projectHistoryDropdown');
        if (!dropdown) {
            // If dropdown doesn't exist yet, try again in 100ms
            setTimeout(loadProjects, 100);
            return;
        }
        
        // Clear and add loading message
        dropdown.innerHTML = '<option value="">Loading projects...</option>';
        
        // Add cache-busting timestamp to prevent browser caching
        const timestamp = new Date().getTime();
        fetch('/api/level1/projects?_t=' + timestamp, { cache: 'no-store' })
            .then(res => res.json())
            .then(data => {
                const projects = data.projects || [];
                dropdown.innerHTML = '<option value="">-- Select a previous project --</option>';
                
                if (projects.length === 0) {
                    const msg = document.getElementById('noProjectsMessage');
                    if (msg) msg.style.display = 'block';
                    dropdown.style.display = 'none';
                    return;
                }
                
                const msg = document.getElementById('noProjectsMessage');
                if (msg) msg.style.display = 'none';
                dropdown.style.display = 'block';
                
                projects.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p.project_name;
                    const date = p.search_date ? new Date(p.search_date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : '';
                    opt.textContent = p.project_name + (date ? ` (${date})` : '') + (p.industry ? ` - ${p.industry}` : '');
                    dropdown.appendChild(opt);
                });
                
                // Handle selection
                dropdown.onchange = function() {
                    if (!this.value) return;
                    window.currentProjectName = this.value;
                    const nameSpan = document.getElementById('currentProjectName');
                    if (nameSpan) nameSpan.textContent = this.value;
                    
                    const form = document.getElementById('searchForm');
                    const start = document.getElementById('startSearchSection');
                    if (form) form.style.display = 'block';
                    if (start) start.style.display = 'none';
                    
                    fetch(`/api/level1/project-data?project_name=${encodeURIComponent(this.value)}`)
                        .then(r => r.json())
                        .then(d => {
                            const pin = document.getElementById('pin_code');
                            const ind = document.getElementById('industry');
                            if (pin && d.pin_codes) pin.value = d.pin_codes;
                            if (ind && d.industry) ind.value = d.industry;
                            if (d.companies && d.companies.length > 0 && typeof displayProjectCompanies === 'function') {
                                displayProjectCompanies(d.companies);
                            }
                        })
                        .catch(e => console.error('Error:', e));
                };
            })
            .catch(err => {
                console.error('Failed to load projects:', err);
                dropdown.innerHTML = '<option value="">Error loading projects</option>';
            });
    }
    
    // Try immediately, then on DOMContentLoaded
    loadProjects();
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadProjects);
    }

    // expose so we can refresh after delete
    window.reloadProjectDropdown = loadProjects;
    
    // Refresh button handler
    function setupRefreshButton() {
        const refreshBtn = document.getElementById('refreshProjectsBtn');
        if (!refreshBtn) {
            setTimeout(setupRefreshButton, 100);
            return;
        }
        refreshBtn.addEventListener('click', function() {
            this.disabled = true;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
            loadProjects();
            setTimeout(() => {
                this.disabled = false;
                this.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
            }, 500);
        });
    }
    setupRefreshButton();
})();

document.addEventListener('DOMContentLoaded', function() {
    
    // Remove duplicate function definitions - we already have it above
    // The function is defined inline above, so we don't need the duplicate
    
    const searchForm = document.getElementById('searchForm');
    const searchBtn = document.getElementById('searchBtn');
    const resultsSection = document.getElementById('resultsSection');
    const errorSection = document.getElementById('errorSection');
    const resultsContainer = document.getElementById('resultsContainer');
    const exportBtn = document.getElementById('exportBtn');
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const deselectAllBtn = document.getElementById('deselectAllBtn');
    const sendToLevel2Btn = document.getElementById('sendToLevel2Btn');
    const selectedCountBadge = document.getElementById('selectedCountBadge');
    const selectedCountSpan = document.getElementById('selectedCount');
    // Removed: State field (not needed - PIN codes are unique in India)
    const pinCodeInput = document.getElementById('pin_code');
    const pinCodeValidation = document.getElementById('pinCodeValidation');
    
    let currentResults = [];
    let selectedCompanies = new Set();
    let currentProjectName = null; // Store project name globally
    
    // Make currentProjectName accessible globally
    Object.defineProperty(window, 'currentProjectName', {
        get: function() { return currentProjectName; },
        set: function(val) { currentProjectName = val; }
    });
    
    // Guard: this script is shared; if the form isn't on the page, just exit quietly
    if (!searchForm || !searchBtn) return;
    
    // Real-time PIN code validation with auto-completion preview
    if (pinCodeInput && pinCodeValidation) {
        pinCodeInput.addEventListener('input', function() {
            const value = this.value.trim();
            if (!value) {
                pinCodeValidation.style.display = 'none';
                return;
            }
            
            // Parse PIN codes (handle trailing commas)
            const allPins = value.split(',')
                .map(p => p.trim())
                .filter(p => p && p.length > 0);
            
            if (allPins.length === 0) {
                pinCodeValidation.style.display = 'none';
                return;
            }
            
            // Separate into valid, incomplete, and invalid
            const validPins = [];
            const incompletePins = [];
            const invalidPins = [];
            const autoCompleted = [];
            
            allPins.forEach(pin => {
                if (/^\d{6}$/.test(pin)) {
                    validPins.push(pin);
                } else if (/^\d+$/.test(pin) && pin.length < 6) {
                    incompletePins.push(pin);
                } else {
                    invalidPins.push(pin);
                }
            });
            
            // Auto-complete incomplete PIN codes using prefix from first valid PIN
            if (validPins.length > 0 && incompletePins.length > 0) {
                const firstValid = validPins[0];
                incompletePins.forEach(incomplete => {
                    const digitsNeeded = 6 - incomplete.length;
                    if (digitsNeeded > 0 && digitsNeeded <= 6 && digitsNeeded <= firstValid.length) {
                        const prefixToUse = firstValid.substring(0, digitsNeeded);
                        const completed = prefixToUse + incomplete;
                        if (/^\d{6}$/.test(completed)) {
                            autoCompleted.push({original: incomplete, completed: completed});
                        }
                    }
                });
            }
            
            // Show validation feedback
            let validationHTML = '';
            const allValidPins = [...validPins, ...autoCompleted.map(ac => ac.completed)];
            
            if (allValidPins.length > 0) {
                validationHTML += `<span style="color: #28a745;"><i class="fas fa-check-circle"></i> ${allValidPins.length} valid: ${allValidPins.join(', ')}</span>`;
            }
            
            if (autoCompleted.length > 0) {
                const autoCompleteText = autoCompleted.map(ac => `${ac.original}→${ac.completed}`).join(', ');
                validationHTML += `<span style="color: #4caf50; margin-left: 10px;"><i class="fas fa-magic"></i> Auto-completed: ${autoCompleteText}</span>`;
            }
            
            // Only show incomplete warning if they can't be auto-completed
            const remainingIncomplete = incompletePins.filter(inc => 
                !autoCompleted.some(ac => ac.original === inc)
            );
            if (remainingIncomplete.length > 0) {
                if (validPins.length === 0) {
                    validationHTML += `<span style="color: #ffc107; margin-left: 10px;"><i class="fas fa-exclamation-circle"></i> Incomplete: ${remainingIncomplete.join(', ')} (enter at least one full 6-digit PIN to auto-complete)</span>`;
                } else {
                    validationHTML += `<span style="color: #ffc107; margin-left: 10px;"><i class="fas fa-exclamation-circle"></i> Incomplete: ${remainingIncomplete.join(', ')} (cannot auto-complete)</span>`;
                }
            }
            
            if (invalidPins.length > 0) {
                validationHTML += `<span style="color: #dc3545; margin-left: 10px;"><i class="fas fa-times-circle"></i> Invalid: ${invalidPins.join(', ')}</span>`;
            }
            
            pinCodeValidation.innerHTML = validationHTML;
            pinCodeValidation.style.display = 'block';
        });
        
        pinCodeInput.addEventListener('blur', function() {
            // Keep validation visible on blur
            if (this.value.trim()) {
                pinCodeValidation.style.display = 'block';
            }
        });
    }

    // Removed: State dropdown code (not needed - PIN codes are unique in India)

    // Progress modal elements
    const progressModal = document.getElementById('progressModal');
    const closeProgressBtn = document.getElementById('closeProgressBtn');
    const progressStage = document.getElementById('progressStage');
    const progressCompaniesFound = document.getElementById('progressCompaniesFound');
    const progressCurrent = document.getElementById('progressCurrent');
    const progressBarFill = document.getElementById('progressBarFill');
    const progressPercentage = document.getElementById('progressPercentage');
    const progressMessage = document.getElementById('progressMessage');
    const progressCompaniesList = document.getElementById('progressCompaniesList');
    
    let eventSource = null; // legacy (kept to avoid runtime errors)
    let currentAbortController = null;
    
    closeProgressBtn.addEventListener('click', function() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        if (currentAbortController) {
            try { currentAbortController.abort(); } catch (_) {}
            currentAbortController = null;
        }
        progressModal.style.display = 'none';
    });
    
    // Function to perform search (extracted so it can be called from both form submit and button click)
    async function performSearch() {
        console.log('🔍 performSearch() called');
        
        // Use stored project name (from modal)
        if (!currentProjectName) {
            showError('Please create a project first');
            if (startSearchBtn) startSearchBtn.click();
            return;
        }
        
        const pinCodesInput = document.getElementById('pin_code')?.value.trim();
        const industry = document.getElementById('industry')?.value.trim();
        
        console.log('Input values:', { projectName: currentProjectName, pinCodesInput, industry });
        
        if (!pinCodesInput) {
            showError('PIN code(s) are required');
            return;
        }
        
        // Parse PIN codes and auto-complete incomplete ones
        // Handle trailing commas, incomplete codes, and invalid entries gracefully
        const allPins = pinCodesInput
            .split(',')
            .map(p => p.trim())
            .filter(p => p && p.length > 0); // Remove empty strings (handles trailing commas)
        
        // Separate into valid, incomplete (numeric but < 6 digits), and invalid
        const validPinCodes = [];
        const incompletePins = [];
        const invalidPins = [];
        
        allPins.forEach(pin => {
            if (/^\d{6}$/.test(pin)) {
                validPinCodes.push(pin);
            } else if (/^\d+$/.test(pin) && pin.length < 6) {
                incompletePins.push(pin);
            } else {
                invalidPins.push(pin);
            }
        });
        
        // Auto-complete incomplete PIN codes using prefix from first valid PIN
        if (validPinCodes.length > 0 && incompletePins.length > 0) {
            const firstValid = validPinCodes[0];
            
            incompletePins.forEach(incomplete => {
                // Calculate how many digits we need from the prefix
                const digitsNeeded = 6 - incomplete.length;
                if (digitsNeeded > 0 && digitsNeeded <= 6) {
                    const prefixToUse = firstValid.substring(0, digitsNeeded);
                    const completed = prefixToUse + incomplete;
                    
                    if (/^\d{6}$/.test(completed)) {
                        validPinCodes.push(completed);
                        console.log(`✅ Auto-completed "${incomplete}" to "${completed}" using prefix from "${firstValid}"`);
                    }
                }
            });
        }
        
        // If no valid PIN codes at all, show error
        if (validPinCodes.length === 0) {
            let errorMsg = 'No valid PIN codes found. ';
            if (incompletePins.length > 0) {
                errorMsg += `Incomplete: ${incompletePins.join(', ')} (need at least one full 6-digit PIN to auto-complete). `;
            }
            if (invalidPins.length > 0) {
                errorMsg += `Invalid: ${invalidPins.join(', ')}. `;
            }
            errorMsg += 'Please enter at least one valid 6-digit PIN code.';
            showError(errorMsg);
            return;
        }
        
        // Show info message if auto-completion happened
        if (incompletePins.length > 0 && validPinCodes.length > incompletePins.length) {
            const autoCompleted = validPinCodes.slice(validPinCodes.length - incompletePins.length);
            let infoMsg = `✅ Auto-completed ${incompletePins.length} PIN code(s): `;
            incompletePins.forEach((incomplete, idx) => {
                infoMsg += `${incomplete} → ${autoCompleted[idx]}; `;
            });
            infoMsg += `Using ${validPinCodes.length} total PIN code(s): ${validPinCodes.join(', ')}.`;
            
            // Show as info, not error
            const infoDiv = document.createElement('div');
            infoDiv.className = 'info-message';
            infoDiv.style.cssText = 'background: #e8f5e9; border-left: 4px solid #4caf50; color: #2e7d32; padding: 12px; border-radius: 6px; margin: 15px 0; display: flex; align-items: center; gap: 10px;';
            infoDiv.innerHTML = `<i class="fas fa-magic"></i> <span>${infoMsg}</span>`;
            resultsSection.insertBefore(infoDiv, resultsSection.firstChild);
            setTimeout(() => infoDiv.remove(), 8000); // Auto-remove after 8 seconds
        }
        
        // Show warning for invalid entries
        if (invalidPins.length > 0) {
            let warnMsg = `⚠️ Skipped invalid entries: ${invalidPins.join(', ')}. `;
            const warnDiv = document.createElement('div');
            warnDiv.className = 'warning-message';
            warnDiv.style.cssText = 'background: #fff3cd; border-left: 4px solid #ffc107; color: #856404; padding: 12px; border-radius: 6px; margin: 15px 0; display: flex; align-items: center; gap: 10px;';
            warnDiv.innerHTML = `<i class="fas fa-exclamation-triangle"></i> <span>${warnMsg}</span>`;
            resultsSection.insertBefore(warnDiv, resultsSection.firstChild);
            setTimeout(() => warnDiv.remove(), 5000);
        }
        
        // Hide previous results and errors (with null checks)
        if (resultsSection) resultsSection.style.display = 'none';
        if (errorSection) errorSection.style.display = 'none';
        
        if (searchBtn) {
            searchBtn.disabled = true;
            const btnText = searchBtn.querySelector('.btn-text');
            const btnLoader = searchBtn.querySelector('.btn-loader');
            if (btnText) btnText.style.display = 'none';
            if (btnLoader) btnLoader.style.display = 'inline';
        }
        
        // Reset progress modal
        currentResults = [];
        if (resultsContainer) resultsContainer.innerHTML = '';
        if (progressCompaniesList) progressCompaniesList.innerHTML = '';
        updateProgress({
            stage: 'Initializing...',
            companies_found: 0,
            current: 0,
            total: 0,
            message: 'Starting search...'
        });
        
        // Show progress modal
        if (progressModal) {
            progressModal.style.display = 'flex';
        } else {
            console.error('❌ progressModal element not found!');
        }
        
        // Generate session ID
        const sessionId = `session_${Date.now()}`;
        
        try {
            // Start Server-Sent Events connection
            const maxCompanies = parseInt(document.getElementById('max_companies').value) || 20;
            
            console.log('🔍 Starting search:', {
                pin_codes: validPinCodes, // Only send valid 6-digit PIN codes
                industry: industry,
                max_companies: maxCompanies
            });

            // If user closes the modal, we abort this request to avoid server-side "broken pipe" noise
            currentAbortController = new AbortController();
            
            // Use Level 1 API endpoint
            const apiEndpoint = window.location.pathname.includes('/level1') ? '/api/level1/search' : '/api/search';
            const response = await fetch(apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                signal: currentAbortController.signal,
                body: JSON.stringify({
                    project_name: currentProjectName,  // User-defined project name (from modal)
                    pin_code: pinCodesInput,  // Send as comma-separated string
                    industry: industry,
                    max_companies: maxCompanies
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || 'Failed to start search');
            }
            
            // Read the stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                
                if (done) {
                    console.log('✅ Stream completed');
                    break;
                }
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            console.log('📦 SSE Event:', data.type, data);
                            handleProgressUpdate(data);
                        } catch (e) {
                            console.error('Error parsing SSE data:', e, line);
                        }
                    }
                }
            }
            
        } catch (error) {
            console.error('Search error:', error);
            // If user aborted (closed modal), don't show as an error
            if (error && (error.name === 'AbortError')) {
                // silently ignore
            } else {
                showError(error.message);
                if (progressModal) progressModal.style.display = 'none';
            }
        } finally {
            currentAbortController = null;
            if (searchBtn) {
                searchBtn.disabled = false;
                const btnText = searchBtn.querySelector('.btn-text');
                const btnLoader = searchBtn.querySelector('.btn-loader');
                if (btnText) btnText.style.display = 'inline';
                if (btnLoader) btnLoader.style.display = 'none';
            }
        }
    }
    
    // Add event listeners
    if (searchForm) {
        searchForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            console.log('📝 Form submit event triggered');
            await performSearch();
        });
    }
    
    // Also add click handler to button as backup
    if (searchBtn) {
        searchBtn.addEventListener('click', async function(e) {
            console.log('🔘 Search button clicked');
            e.preventDefault();
            e.stopPropagation();
            
            // Check if project name is set
            if (!currentProjectName) {
                alert('Please create a project first');
                if (startSearchBtn) startSearchBtn.click();
                return;
            }
            
            await performSearch();
        });
    }
    
    // Project Name Modal handlers
    const projectNameModal = document.getElementById('projectNameModal');
    const projectNameInput = document.getElementById('project_name_input');
    const confirmProjectBtn = document.getElementById('confirmProjectBtn');
    const cancelProjectBtn = document.getElementById('cancelProjectBtn');
    const startSearchBtn = document.getElementById('startSearchBtn');
    const startSearchSection = document.getElementById('startSearchSection');
    const changeProjectBtn = document.getElementById('changeProjectBtn');
    const currentProjectNameSpan = document.getElementById('currentProjectName');
    const projectHistoryDropdown = document.getElementById('projectHistoryDropdown');

    // NOTE: Project history loading is handled at the TOP of this file (before guard clause)
    // This ensures it runs even if searchForm doesn't exist
    // No need to duplicate the function here
    
    // Check if project name exists
    async function checkProjectExists(projectName) {
        if (!projectName || projectName.length < 3) return false;
        
        try {
            const response = await fetch('/api/level1/check-project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project_name: projectName })
            });
            const data = await response.json();
            return data.exists || false;
        } catch (error) {
            console.error('Error checking project:', error);
            return false;
        }
    }
    
    // Show project name modal when "Start Search" is clicked
    if (startSearchBtn) {
        startSearchBtn.addEventListener('click', async function() {
            console.log('🔘 Start Search button clicked');
            if (projectNameModal) {
                // (removed) project history inside modal
                
                projectNameModal.style.display = 'flex';
                if (projectNameInput) {
                    projectNameInput.focus();
                    projectNameInput.value = '';
                }
            } else {
                console.error('❌ projectNameModal not found');
            }
        });
    }
    
    // (removed) projectHistorySelect inside modal
    
    // Check for duplicate project name as user types
    if (projectNameInput) {
        let checkTimeout;
        projectNameInput.addEventListener('input', function() {
            clearTimeout(checkTimeout);
            const projectName = this.value.trim();
            const warningDiv = document.getElementById('projectNameWarning');
            
            if (projectName.length >= 3) {
                checkTimeout = setTimeout(async () => {
                    const exists = await checkProjectExists(projectName);
                    if (warningDiv) {
                        warningDiv.style.display = exists ? 'block' : 'none';
                    }
                }, 500); // Debounce: check after 500ms of no typing
            } else {
                if (warningDiv) warningDiv.style.display = 'none';
            }
        });
    }

    // Change project button
    if (changeProjectBtn) {
        changeProjectBtn.addEventListener('click', function() {
            if (projectNameModal) {
                projectNameModal.style.display = 'flex';
                if (projectNameInput) {
                    projectNameInput.focus();
                    projectNameInput.value = currentProjectName || '';
                }
            }
        });
    }

    // NOTE: "Delete Project" button removed from this section as requested

    // Cancel project modal
    if (cancelProjectBtn) {
        cancelProjectBtn.addEventListener('click', function() {
            if (projectNameModal) projectNameModal.style.display = 'none';
        });
    }

    // Confirm project name
    if (confirmProjectBtn && projectNameInput) {
        confirmProjectBtn.addEventListener('click', async function() {
            const projectName = projectNameInput.value.trim();
            const errorDiv = document.getElementById('projectNameError');
            
            // Validate
            if (!projectName) {
                if (errorDiv) {
                    errorDiv.textContent = 'Project name is required';
                    errorDiv.style.display = 'block';
                }
                return;
            }
            
            if (projectName.length < 3) {
                if (errorDiv) {
                    errorDiv.textContent = 'Project name must be at least 3 characters';
                    errorDiv.style.display = 'block';
                }
                return;
            }
            
            if (projectName.length > 100) {
                if (errorDiv) {
                    errorDiv.textContent = 'Project name must be less than 100 characters';
                    errorDiv.style.display = 'block';
                }
                return;
            }
            
            if (!/^[a-zA-Z0-9\s\-_]+$/.test(projectName)) {
                if (errorDiv) {
                    errorDiv.textContent = 'Project name can only contain letters, numbers, spaces, hyphens, and underscores';
                    errorDiv.style.display = 'block';
                }
                return;
            }
            
            // Hide error and warning
            if (errorDiv) errorDiv.style.display = 'none';
            const warningDiv = document.getElementById('projectNameWarning');
            if (warningDiv) warningDiv.style.display = 'none';
            
            // Check if project exists (show warning but allow)
            const exists = await checkProjectExists(projectName);
            if (exists) {
                // Show warning but allow user to proceed
                if (warningDiv) {
                    warningDiv.style.display = 'block';
                }
                // Ask user if they want to continue
                if (!confirm('This project already exists. New companies will be added to the existing project. Continue?')) {
                    return;
                }
            }
            
            // Store project name
            currentProjectName = projectName;
            console.log('✅ Project name set:', currentProjectName);
            
            // Hide modal
            if (projectNameModal) projectNameModal.style.display = 'none';
            
            // Show search form and hide start section
            if (searchForm) searchForm.style.display = 'block';
            if (startSearchSection) startSearchSection.style.display = 'none';
            
            // Update current project display
            if (currentProjectNameSpan) currentProjectNameSpan.textContent = projectName;
            
            // If this is an existing project, load its data
            if (exists) {
                try {
                    const response = await fetch(`/api/level1/project-data?project_name=${encodeURIComponent(projectName)}`);
                    const projectData = await response.json();
                    
                    if (response.ok && projectData.companies && projectData.companies.length > 0) {
                        // Pre-fill form fields
                        const pinCodeInput = document.getElementById('pin_code');
                        const industryInput = document.getElementById('industry');
                        
                        if (pinCodeInput && projectData.pin_codes) {
                            pinCodeInput.value = projectData.pin_codes;
                        }
                        if (industryInput && projectData.industry) {
                            industryInput.value = projectData.industry;
                        }
                        
                        // Display existing companies
                        displayProjectCompanies(projectData.companies);
                    }
                } catch (error) {
                    console.error('Error loading project data:', error);
                }
            }
            
            // If this is an existing project, load its data
            if (exists) {
                try {
                    const response = await fetch(`/api/level1/project-data?project_name=${encodeURIComponent(projectName)}`);
                    const projectData = await response.json();
                    
                    if (response.ok && projectData.companies && projectData.companies.length > 0) {
                        // Pre-fill form fields
                        const pinCodeInput = document.getElementById('pin_code');
                        const industryInput = document.getElementById('industry');
                        
                        if (pinCodeInput && projectData.pin_codes) {
                            pinCodeInput.value = projectData.pin_codes;
                        }
                        if (industryInput && projectData.industry) {
                            industryInput.value = projectData.industry;
                        }
                        
                        // Display existing companies
                        displayProjectCompanies(projectData.companies);
                    }
                } catch (error) {
                    console.error('Error loading project data:', error);
                }
            }
        });
        
        // Allow Enter key to confirm
        if (projectNameInput) {
            projectNameInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    confirmProjectBtn.click();
                }
            });
        }
    }
    
    function handleProgressUpdate(evt) {
        // evt = { type: 'progress'|'company_update'|'complete'|'error', data: {...}, progress?: {...} }
        try {
            if (!evt || !evt.type) return;

            if (evt.type === 'progress') {
                updateProgress(evt.data || {});
                return;
            }

            if (evt.type === 'company_update') {
                // Add company to results in real-time (lazy loading)
                if (evt.data) addCompanyToResults(evt.data);

                // Update progress bar + counters
                const p = evt.progress || {};
                updateProgress({
                    // Level 1 is not enrichment; this is just streaming company results
                    stage: 'processing_companies',
                    companies_found: p.total,
                    current: p.current,
                    total: p.total,
                    message: (evt.data && evt.data.company_name)
                        ? `Processing ${evt.data.company_name}... (${p.current || 0}/${p.total || 0})`
                        : 'Processing companies...'
                });
                return;
            }

            if (evt.type === 'complete') {
                const payload = evt.data || {};
                currentResults = payload.companies || [];

                const totalCompanies = payload.total_companies || 0;
                updateProgress({
                    stage: 'Complete',
                    companies_found: totalCompanies,
                    current: totalCompanies,
                    total: totalCompanies,
                    message: totalCompanies > 0 ? 'Search completed!' : (payload.message || 'No companies found')
                });

                // Update final stats
                const companyCountEl = document.getElementById('companyCount');
                if (companyCountEl) companyCountEl.textContent = totalCompanies;

                // Show results section (even if empty, so user sees message)
                if (resultsSection) resultsSection.style.display = 'block';
                
                // Show/hide export and save buttons based on results
                if (exportBtn) {
                    exportBtn.style.display = totalCompanies > 0 ? 'inline-block' : 'none';
                }
                const saveProjectBtn = document.getElementById('saveProjectBtn');
                if (saveProjectBtn) {
                    saveProjectBtn.style.display = totalCompanies > 0 ? 'inline-block' : 'none';
                }

                if (totalCompanies === 0) {
                    showError(payload.message || 'No companies found for the given location. Please try a different PIN code or state.');
                }

                // Hide progress modal after a short delay
                setTimeout(() => {
                    if (progressModal) progressModal.style.display = 'none';
                }, 1200);
                return;
            }

            if (evt.type === 'error') {
                const errMsg = (evt.data && evt.data.error) ? evt.data.error : 'An error occurred during search';
                showError(errMsg);
                if (progressModal) progressModal.style.display = 'none';
                return;
            }
        } catch (e) {
            console.error('handleProgressUpdate failed:', e, evt);
            // Only show error if it's not a null reference (which we've now fixed)
            if (progressModal) progressModal.style.display = 'none';
            // Don't show generic error - let the actual error be logged to console
        }
    }
    
    function formatStageLabel(stage) {
        if (!stage) return '';
        const map = {
            searching_places: 'Searching Google Places',
            saving: 'Saving to Google Sheets',
            processing_companies: 'Building Results',
            complete: 'Complete',
            Complete: 'Complete',
        };
        if (map[stage]) return map[stage];
        // Fallback: make it readable (snake_case -> Title Case)
        return String(stage)
            .replace(/_/g, ' ')
            .replace(/\b\w/g, (c) => c.toUpperCase());
    }

    function updateProgress(progress) {
        if (!progress) return;
        
        try {
            if (progress.stage && progressStage) {
                progressStage.textContent = formatStageLabel(progress.stage);
            }
            if (progress.companies_found !== undefined && progressCompaniesFound) {
                progressCompaniesFound.textContent = progress.companies_found;
            }
            if (progress.current !== undefined && progress.total !== undefined) {
                if (progressCurrent) {
                    const stage = progress.stage || '';
                    if (stage === 'searching_places') {
                        progressCurrent.textContent = `PIN ${progress.current} / ${progress.total}`;
                    } else if (stage === 'saving') {
                        progressCurrent.textContent = `Saving ${progress.current} / ${progress.total}`;
                    } else {
                        progressCurrent.textContent = `Company ${progress.current} / ${progress.total}`;
                    }
                }
                
                // Update progress bar
                const percentage = progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;
                if (progressBarFill) {
                    progressBarFill.style.width = `${percentage}%`;
                }
                if (progressPercentage) {
                    progressPercentage.textContent = `${percentage}%`;
                }
            }
            if (progress.message && progressMessage) {
                progressMessage.textContent = progress.message;
            }
        } catch (e) {
            console.error('Error updating progress:', e);
        }
    }
    
    function addCompanyToResults(company) {
        // Add company card to results container (lazy loading)
        const companyCard = createCompanyCard(company);
        resultsContainer.appendChild(companyCard);
        
        // Add checkbox event listener
        const checkbox = companyCard.querySelector('.company-checkbox');
        if (checkbox) {
            checkbox.addEventListener('change', function() {
                const companyId = this.getAttribute('data-company-id');
                if (this.checked) {
                    selectedCompanies.add(companyId);
                } else {
                    selectedCompanies.delete(companyId);
                }
                updateSelectionUI();
            });
        }
        
        // Show selection buttons when first company is added
        if (selectAllBtn) selectAllBtn.style.display = 'inline-block';
        if (deselectAllBtn) deselectAllBtn.style.display = 'inline-block';
        if (deleteSelectedBtn) deleteSelectedBtn.style.display = 'inline-block';
        if (sendToLevel2Btn) sendToLevel2Btn.style.display = 'inline-block';
        
        // Also add to progress list
        const listItem = document.createElement('div');
        listItem.className = 'progress-company-item';
        listItem.innerHTML = `
            <span class="company-name-small">${escapeHtml(company.company_name || 'N/A')}</span>
            <span class="checkmark">✓</span>
        `;
        progressCompaniesList.appendChild(listItem);
        
        // Scroll to bottom of progress list
        progressCompaniesList.scrollTop = progressCompaniesList.scrollHeight;
    }
    
    function updateSelectionUI() {
        const count = selectedCompanies.size;
        if (selectedCountSpan) selectedCountSpan.textContent = count;
        if (selectedCountBadge) {
            selectedCountBadge.style.display = count > 0 ? 'inline-flex' : 'none';
        }
        if (sendToLevel2Btn) {
            sendToLevel2Btn.disabled = count === 0;
        }
    }
    
    // Display companies from a previous project
    function displayProjectCompanies(companies) {
        if (!companies || companies.length === 0) return;
        
        // Clear existing results
        if (resultsContainer) resultsContainer.innerHTML = '';
        if (progressCompaniesList) progressCompaniesList.innerHTML = '';
        selectedCompanies.clear();
        
        // Store companies globally
        currentResults = companies;
        
        // Show results section
        const resultsSection = document.getElementById('resultsSection');
        if (resultsSection) resultsSection.style.display = 'block';

        // Update company count badge
        const companyCountEl = document.getElementById('companyCount');
        if (companyCountEl) companyCountEl.textContent = String(companies.length);
        
        // Display each company
        companies.forEach(company => {
            addCompanyToResults(company);
            
            // If company was previously selected for Level 2, check the checkbox
            if (company.selected_for_level2) {
                const companyId = company.place_id || company.company_name;
                selectedCompanies.add(companyId);
                
                // Also check the checkbox visually
                const checkbox = resultsContainer.querySelector(`[data-company-id="${companyId}"]`);
                if (checkbox) checkbox.checked = true;
            }
        });
        
        // Update selection UI
        updateSelectionUI();
        
        // Show export and save buttons
        const exportBtn = document.getElementById('exportBtn');
        if (exportBtn) exportBtn.style.display = 'inline-block';
        const saveProjectBtn = document.getElementById('saveProjectBtn');
        if (saveProjectBtn) saveProjectBtn.style.display = 'inline-block';
        
        console.log(`✅ Loaded ${companies.length} companies from previous project`);
    }

    // Expose for the early "loadProjects" dropdown initializer (top of file)
    // This keeps the existing closure variables (resultsContainer, selectedCompanies, etc.)
    window.displayProjectCompanies = displayProjectCompanies;
    
    // Select All functionality
    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', function() {
            const checkboxes = resultsContainer.querySelectorAll('.company-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = true;
                const companyId = cb.getAttribute('data-company-id');
                selectedCompanies.add(companyId);
            });
            updateSelectionUI();
        });
    }
    
    // Deselect All functionality
    if (deselectAllBtn) {
        deselectAllBtn.addEventListener('click', function() {
            const checkboxes = resultsContainer.querySelectorAll('.company-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = false;
            });
            selectedCompanies.clear();
            updateSelectionUI();
        });
    }
    
    // Send Selected to Level 2
    if (sendToLevel2Btn) {
        sendToLevel2Btn.addEventListener('click', async function() {
            const selected = Array.from(selectedCompanies).map(id => {
                return currentResults.find(c => (c.place_id || c.company_name) === id);
            }).filter(c => c !== undefined);
            
            if (selected.length === 0) {
                alert('Please select at least one company');
                return;
            }
            
            this.disabled = true;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
            
            try {
                // Include project_name so Level 2 knows which project these companies belong to
                const response = await fetch('/api/level1/select-for-level2', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        companies: selected,
                        project_name: currentProjectName  // Include project name
                    })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    alert(`✅ Successfully sent ${selected.length} companies to Level 2!`);
                    // Optionally redirect to Level 2
                    if (confirm('Go to Level 2 to start enrichment?')) {
                        window.location.href = '/level2';
                    }
                } else {
                    throw new Error(data.error || 'Failed to send companies to Level 2');
                }
            } catch (error) {
                alert('Error: ' + error.message);
            } finally {
                this.disabled = false;
                this.innerHTML = '<i class="fas fa-paper-plane"></i> Send Selected to Level 2';
            }
        });
    }

    // Delete Selected companies (from Supabase)
    if (deleteSelectedBtn) {
        deleteSelectedBtn.addEventListener('click', async function() {
            if (!currentProjectName) {
                alert('Please select a project first');
                return;
            }
            const identifiers = Array.from(selectedCompanies);
            if (identifiers.length === 0) {
                alert('Please select at least one company to delete');
                return;
            }
            if (!confirm(`Delete ${identifiers.length} selected company(s) from database? This cannot be undone.`)) {
                return;
            }

            this.disabled = true;
            const oldHtml = this.innerHTML;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deleting...';

            try {
                const resp = await fetch('/api/level1/delete-companies', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        project_name: currentProjectName,
                        identifiers
                    })
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(data.error || 'Delete failed');

                // Remove deleted from currentResults and re-render
                const idSet = new Set(identifiers);
                currentResults = (currentResults || []).filter(c => {
                    const id = (c.place_id || c.company_name);
                    return !idSet.has(id);
                });
                selectedCompanies.clear();
                if (typeof window.displayProjectCompanies === 'function') {
                    window.displayProjectCompanies(currentResults);
                }
                alert(`✅ Deleted ${data.deleted || identifiers.length} company(s) from database`);

            } catch (e) {
                alert('Delete failed: ' + (e.message || e));
            } finally {
                this.disabled = false;
                this.innerHTML = oldHtml;
            }
        });
    }
    
    function displayResults(data) {
        // This function is kept for compatibility but results are now added via lazy loading
        const companies = data.companies || [];
        
        if (companies.length === 0) {
            showError('No companies found for the given location');
            return;
        }
        
        document.getElementById('companyCount').textContent = data.total_companies || companies.length;
        
        // Results are already added via lazy loading, just show the section
        if (resultsContainer.children.length === 0) {
            companies.forEach(company => {
                const companyCard = createCompanyCard(company);
                resultsContainer.appendChild(companyCard);
            });
        }
        
        resultsSection.style.display = 'block';
    }
    
    function createCompanyCard(company) {
        const card = document.createElement('div');
        card.className = 'company-card';
        card.setAttribute('data-company-id', company.place_id || company.company_name);
        
        // Level 1: Only show Google Places data - NO contacts
        card.innerHTML = `
            <div class="company-header">
                <div class="company-title-section">
                    <label class="company-checkbox-wrapper">
                        <input type="checkbox" class="company-checkbox" data-company-id="${company.place_id || company.company_name}">
                        <span class="checkbox-custom"></span>
                    </label>
                    <div class="company-icon">
                        <i class="fas fa-building"></i>
                    </div>
                    <div>
                        <div class="company-name">${escapeHtml(company.company_name || 'N/A')}</div>
                        <span class="company-industry">
                            <i class="fas fa-tag"></i> ${escapeHtml(company.industry || 'General Business')}
                        </span>
                    </div>
                </div>
            </div>
            
            <div class="company-info">
                <div class="info-item">
                    <i class="fas fa-globe"></i>
                    <div class="info-content">
                        <strong>WEBSITE</strong>
                        <span>${company.website ? `<a href="${company.website}" target="_blank">${escapeHtml(company.website)}</a>` : '<span class="na-text">N/A</span>'}</span>
                    </div>
                </div>
                <div class="info-item">
                    <i class="fas fa-phone"></i>
                    <div class="info-content">
                        <strong>PHONE</strong>
                        <span>${company.phone ? `<a href="tel:${company.phone}">${escapeHtml(company.phone)}</a>` : '<span class="na-text">N/A</span>'}</span>
                    </div>
                </div>
                <div class="info-item">
                    <i class="fas fa-map-marker-alt"></i>
                    <div class="info-content">
                        <strong>ADDRESS</strong>
                        <span>${escapeHtml(company.address || 'N/A')}</span>
                    </div>
                </div>
            </div>
        `;
        
        return card;
    }
    
    // Removed: createContactCard and toggleContactDetails functions
    // These are not needed in Level 1 (contacts are handled in Level 2)
    
    function showError(message) {
        errorSection.style.display = 'block';
        document.getElementById('errorMessage').textContent = message;
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Handle "Back to Start" button - reset to initial view
    // NOTE: startSearchSection/currentProjectNameSpan/resultsSection are already declared above in this scope.
    const backToStartBtn = document.getElementById('backToStartBtn');
    
    if (backToStartBtn) {
        backToStartBtn.addEventListener('click', function() {
            // Always scroll to the start section so user sees an obvious change
            try {
                if (startSearchSection && typeof startSearchSection.scrollIntoView === 'function') {
                    startSearchSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                } else {
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                }
            } catch (_) {
                window.scrollTo(0, 0);
            }

            // Hide search form
            if (searchForm) searchForm.style.display = 'none';
            
            // Show start section (project selection)
            if (startSearchSection) startSearchSection.style.display = 'block';

            // Visual feedback (flash highlight) so user knows reset happened
            try {
                if (startSearchSection) {
                    startSearchSection.classList.remove('flash-highlight');
                    // force reflow
                    void startSearchSection.offsetWidth;
                    startSearchSection.classList.add('flash-highlight');
                }
            } catch (_) {}
            
            // Clear project name
            currentProjectName = null;
            if (currentProjectNameSpan) currentProjectNameSpan.textContent = '';
            
            // Clear form fields
            const pinCodeInput = document.getElementById('pin_code');
            const industryInput = document.getElementById('industry');
            if (pinCodeInput) pinCodeInput.value = '';
            if (industryInput) industryInput.value = '';
            
            // Clear results
            if (resultsContainer) resultsContainer.innerHTML = '';
            if (resultsSection) resultsSection.style.display = 'none';
            currentResults = [];
            selectedCompanies.clear();

            // Reset counters/badges/buttons
            const companyCountEl = document.getElementById('companyCount');
            if (companyCountEl) companyCountEl.textContent = '0';
            if (selectedCountSpan) selectedCountSpan.textContent = '0';
            if (selectedCountBadge) selectedCountBadge.style.display = 'none';
            if (selectAllBtn) selectAllBtn.style.display = 'none';
            if (deselectAllBtn) deselectAllBtn.style.display = 'none';
            if (sendToLevel2Btn) sendToLevel2Btn.style.display = 'none';
            if (exportBtn) exportBtn.style.display = 'none';
            if (deleteSelectedBtn) deleteSelectedBtn.style.display = 'none';
            const saveProjectBtnReset = document.getElementById('saveProjectBtn');
            if (saveProjectBtnReset) saveProjectBtnReset.style.display = 'none';
            
            // Reset dropdown and RELOAD project list from server
            const projectHistoryDropdown = document.getElementById('projectHistoryDropdown');
            if (projectHistoryDropdown) projectHistoryDropdown.value = '';
            
            // IMPORTANT: Reload project list to show newly created projects
            if (window.reloadProjectDropdown) {
                window.reloadProjectDropdown();
            }
            
            console.log('✅ Reset to start view');
        });
    }
    
    exportBtn.addEventListener('click', async function() {
        if (currentResults.length === 0) {
            alert('No data to export');
            return;
        }
        
        try {
            this.disabled = true;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Exporting...';
            
            const response = await fetch('/api/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    companies: currentResults,
                    project_name: currentProjectName || 'companies'
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || 'Export failed');
            }
            
            // Download Excel file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const safeProjectName = (currentProjectName || 'companies').replace(/[^a-zA-Z0-9\s\-_]/g, '').substring(0, 50);
            a.download = `${safeProjectName}_companies.xlsx`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
        } catch (error) {
            alert('Export failed: ' + error.message);
        } finally {
            this.disabled = false;
            this.innerHTML = '<i class="fas fa-download"></i> Export to Excel';
        }
    });
    
    // Save Project button handler
    const saveProjectBtn = document.getElementById('saveProjectBtn');
    if (saveProjectBtn) {
        saveProjectBtn.addEventListener('click', async function() {
            if (!currentProjectName) {
                alert('No project name set');
                return;
            }
            
            this.disabled = true;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
            
            try {
                // The data is already saved when search completes
                // Just refresh the project list to confirm
                if (window.reloadProjectDropdown) {
                    window.reloadProjectDropdown();
                }
                
                // Show success message
                this.innerHTML = '<i class="fas fa-check"></i> Saved!';
                this.style.background = '#2f855a';
                
                setTimeout(() => {
                    this.innerHTML = '<i class="fas fa-save"></i> Save Project';
                    this.style.background = '#38a169';
                    this.disabled = false;
                }, 2000);
                
                alert('✅ Project "' + currentProjectName + '" saved successfully!\n\nYou can now click "Back to Start" to see it in Previous Projects.');
                
            } catch (error) {
                alert('Save failed: ' + error.message);
                this.disabled = false;
                this.innerHTML = '<i class="fas fa-save"></i> Save Project';
            }
        });
    }
    
    function convertToCSV(data) {
        if (data.length === 0) return '';
        
        const headers = Object.keys(data[0]);
        const csvRows = [headers.join(',')];
        
        data.forEach(row => {
            const values = headers.map(header => {
                const value = row[header] || '';
                // Escape commas and quotes in CSV
                if (value.includes(',') || value.includes('"') || value.includes('\n')) {
                    return `"${value.replace(/"/g, '""')}"`;
                }
                return value;
            });
            csvRows.push(values.join(','));
        });
        
        return csvRows.join('\n');
    }
    
    function downloadCSV(csv, filename) {
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    }
});

