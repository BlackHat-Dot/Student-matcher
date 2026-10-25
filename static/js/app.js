/**
 * Dynamic Matcher Frontend Client
 * 
 * Features:
 * - Two modes: "One Student & Best 5 Show" and "Compare Two Students (1 vs 1)"
 * - Instant client-side prefix & token autocomplete (prefetched on load).
 * - Multi-token matching (names, stripped names, registration numbers).
 * - Full keyboard navigation (Arrow Up/Down, Enter, Tab, Escape).
 * - Strict validation: disallows comparing two same students.
 * - Explicit student presence verification with hard block and descriptive error banners.
 * - Top 5 Best Matches engine utilizing Inverted Index + Min-Heap.
 * - Detailed course-by-course breakdown for both 1-vs-1 and Top 5 cards.
 */

class StudentIndex {
  constructor() {
    this.students = [];
    this.prefixMap = new Map(); // prefix -> Set of student indices
    this.isLoaded = false;
  }

  load(studentsData) {
    this.students = studentsData;
    this.prefixMap.clear();

    for (let i = 0; i < this.students.length; i++) {
      const s = this.students[i];
      const tokens = new Set();

      const fullWords = (s.name || '').toLowerCase().match(/[a-z0-9]+/g) || [];
      fullWords.forEach(w => tokens.add(w));

      const displayWords = (s.display_name || '').toLowerCase().match(/[a-z0-9]+/g) || [];
      displayWords.forEach(w => tokens.add(w));

      if (s.reg_no) {
        tokens.add(s.reg_no.toLowerCase());
      }

      tokens.forEach(tok => {
        const maxLen = Math.min(tok.length, 20);
        for (let len = 1; len <= maxLen; len++) {
          const prefix = tok.slice(0, len);
          if (!this.prefixMap.has(prefix)) {
            this.prefixMap.set(prefix, new Set());
          }
          this.prefixMap.get(prefix).add(i);
        }
      });
    }

    this.isLoaded = true;
  }

  search(query, limit = 8) {
    const q = (query || '').trim().toLowerCase();
    if (!q || !this.isLoaded) return [];

    let candidateIndices = this.prefixMap.get(q) ? Array.from(this.prefixMap.get(q)) : [];

    if (candidateIndices.length < limit) {
      const seen = new Set(candidateIndices);
      for (let i = 0; i < this.students.length; i++) {
        if (!seen.has(i)) {
          const s = this.students[i];
          if ((s.name && s.name.toLowerCase().includes(q)) || 
              (s.reg_no && s.reg_no.toLowerCase().includes(q))) {
            candidateIndices.push(i);
            if (candidateIndices.length >= limit * 3) break;
          }
        }
      }
    }

    const candidates = candidateIndices.map(idx => this.students[idx]);

    candidates.sort((a, b) => {
      const aLower = a.name.toLowerCase();
      const bLower = b.name.toLowerCase();
      const aClean = (a.display_name || '').toLowerCase();
      const bClean = (b.display_name || '').toLowerCase();
      const aReg = (a.reg_no || '').toLowerCase();
      const bReg = (b.reg_no || '').toLowerCase();

      const getScore = (name, clean, reg) => {
        if (name.startsWith(q) || clean.startsWith(q)) return 0;
        if (reg && reg.startsWith(q)) return 1;
        const words = name.split(/\s+/);
        if (words.some(w => w.startsWith(q))) return 2;
        return 3;
      };

      const scoreA = getScore(aLower, aClean, aReg);
      const scoreB = getScore(bLower, bClean, bReg);

      if (scoreA !== scoreB) return scoreA - scoreB;
      return a.name.length - b.name.length;
    });

    return candidates.slice(0, limit);
  }

  findStudent(query) {
    const q = (query || '').trim().toLowerCase();
    if (!q || !this.isLoaded) return null;

    // 1. Exact match on full name
    const exact = this.students.find(s => s.name.toLowerCase() === q);
    if (exact) return exact;

    // 2. Exact match on clean display name
    const cleanMatch = this.students.find(s => (s.display_name || '').toLowerCase() === q);
    if (cleanMatch) return cleanMatch;

    // 3. Exact match on registration number
    const regMatch = this.students.find(s => (s.reg_no || '').toLowerCase() === q);
    if (regMatch) return regMatch;

    // 4. Case-insensitive substring match if uniquely resolves
    const matches = this.students.filter(s => 
      s.name.toLowerCase().includes(q) || 
      (s.reg_no && s.reg_no.toLowerCase().includes(q))
    );
    if (matches.length === 1) return matches[0];

    return null;
  }

  getRandomStudent() {
    if (!this.students || this.students.length === 0) return null;
    const idx = Math.floor(Math.random() * this.students.length);
    return this.students[idx];
  }

  getRandomPair() {
    if (!this.students || this.students.length < 2) return null;
    const idxA = Math.floor(Math.random() * this.students.length);
    let idxB = Math.floor(Math.random() * this.students.length);
    while (idxB === idxA) {
      idxB = Math.floor(Math.random() * this.students.length);
    }
    return [this.students[idxA], this.students[idxB]];
  }
}

// UI Controller
class MatcherApp {
  constructor() {
    this.index = new StudentIndex();
    this.currentMode = 'top5'; // 'top5' or 'pair'
    this.currentComparisons = [];
    this.activeFilter = 'all';

    // Mode Switcher Elements
    this.modeTop5Btn = document.getElementById('mode-top5-btn');
    this.modePairBtn = document.getElementById('mode-pair-btn');
    this.modeTitle = document.getElementById('mode-title');
    this.modeDesc = document.getElementById('mode-desc');
    this.formTop5 = document.getElementById('form-top5');
    this.formPair = document.getElementById('form-pair');

    // Single Input Elements (Top 5 mode)
    this.inputSingle = document.getElementById('student-single');
    this.dropdownSingle = document.getElementById('dropdown-single');
    this.clearSingle = document.getElementById('clear-single');
    this.metaSingle = document.getElementById('meta-single');
    this.submitTop5Btn = document.getElementById('submit-top5-btn');

    // Pair Input Elements (1 vs 1 mode)
    this.inputA = document.getElementById('student-a');
    this.inputB = document.getElementById('student-b');
    this.dropdownA = document.getElementById('dropdown-a');
    this.dropdownB = document.getElementById('dropdown-b');
    this.clearA = document.getElementById('clear-a');
    this.clearB = document.getElementById('clear-b');
    this.metaA = document.getElementById('meta-a');
    this.metaB = document.getElementById('meta-b');
    this.swapBtn = document.getElementById('swap-btn');
    this.submitPairBtn = document.getElementById('submit-match-btn');

    // Global Action Elements
    this.randomBtn = document.getElementById('random-btn');
    this.randomBtnLabel = document.getElementById('random-btn-label');
    this.errorBanner = document.getElementById('error-banner');
    this.errorTitle = document.getElementById('error-title');
    this.errorMessage = document.getElementById('error-message');
    this.errorClose = document.getElementById('error-close');
    this.emptyState = document.getElementById('empty-state');
    this.dbStatusChip = document.getElementById('db-status-chip');
    this.dbStatusText = document.getElementById('db-status-text');

    // Results Containers
    this.top5ResultsSection = document.getElementById('top5-results-section');
    this.top5TargetTitle = document.getElementById('top5-target-title');
    this.top5TargetSub = document.getElementById('top5-target-sub');
    this.top5CardsList = document.getElementById('top5-cards-list');

    this.pairResultsSection = document.getElementById('results-section');
    this.breakdownTbody = document.getElementById('breakdown-tbody');
    this.countAll = document.getElementById('count-all');
    this.countMatched = document.getElementById('count-matched');
    this.countMismatched = document.getElementById('count-mismatched');
    this.countUnavailable = document.getElementById('count-unavailable');
    this.tabButtons = document.querySelectorAll('.tab-btn');

    // Additional courses elements
    this.additionalToggle = document.getElementById('additional-toggle');
    this.additionalContent = document.getElementById('additional-content');
    this.additionalGrid = document.getElementById('additional-grid');
    this.additionalCount = document.getElementById('additional-count');
    this.additionalWrap = document.getElementById('additional-courses-wrap');

    this.init();
  }

  async init() {
    this.setupEventListeners();
    await this.prefetchStudents();
  }

  async prefetchStudents() {
    try {
      this.dbStatusText.textContent = 'Loading students';
      const response = await fetch('/api/students');
      if (!response.ok) throw new Error('Failed to load student index');
      const data = await response.json();

      this.index.load(data.students || []);
      this.dbStatusText.textContent = `${this.index.students.length} students`;
      this.dbStatusChip.style.borderColor = 'rgba(16, 185, 129, 0.4)';
    } catch (err) {
      console.error('Error prefetching student index:', err);
      this.dbStatusText.textContent = 'Index load failed';
      this.dbStatusChip.style.borderColor = 'rgba(244, 63, 94, 0.4)';
    }
  }

  setupEventListeners() {
    // Mode Switcher
    this.modeTop5Btn.addEventListener('click', () => this.switchMode('top5'));
    this.modePairBtn.addEventListener('click', () => this.switchMode('pair'));

    // Autocomplete setup
    this.setupAutocomplete(this.inputSingle, this.dropdownSingle, this.clearSingle, this.metaSingle, () => this.calculateTop5());
    this.setupAutocomplete(this.inputA, this.dropdownA, this.clearA, this.metaA, () => this.calculatePairMatch());
    this.setupAutocomplete(this.inputB, this.dropdownB, this.clearB, this.metaB, () => this.calculatePairMatch());

    // Submit actions
    this.submitTop5Btn.addEventListener('click', () => this.calculateTop5());
    this.submitPairBtn.addEventListener('click', () => this.calculatePairMatch());

    // Swap and Random
    this.swapBtn.addEventListener('click', () => this.swapStudents());
    this.randomBtn.addEventListener('click', () => this.handleRandomClick());

    // Error Close
    this.errorClose.addEventListener('click', () => this.hideError());

    // Tabs for 1-vs-1 breakdown
    this.tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        this.tabButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.activeFilter = btn.dataset.filter;
        this.renderPairBreakdownTable();
      });
    });

    // Additional courses accordion
    this.additionalToggle.addEventListener('click', () => {
      const isHidden = this.additionalContent.hidden;
      this.additionalContent.hidden = !isHidden;
      this.additionalToggle.classList.toggle('open', isHidden);
    });

    // Close dropdowns on outside click
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#wrapper-single')) this.hideDropdown(this.dropdownSingle);
      if (!e.target.closest('#wrapper-a')) this.hideDropdown(this.dropdownA);
      if (!e.target.closest('#wrapper-b')) this.hideDropdown(this.dropdownB);
    });
  }

  switchMode(mode) {
    if (this.currentMode === mode) return;
    this.currentMode = mode;
    this.hideError();
    this.hideAllResults();

    if (mode === 'top5') {
      this.modeTop5Btn.classList.add('active');
      this.modePairBtn.classList.remove('active');
      this.formTop5.hidden = false;
      this.formPair.hidden = true;
      this.modeTitle.textContent = 'Who shares your slots?';
      this.modeDesc.textContent = 'Pick a student. We rank everyone else by how many theory slots they share.';
      this.randomBtnLabel.textContent = 'Random student';
    } else {
      this.modePairBtn.classList.add('active');
      this.modeTop5Btn.classList.remove('active');
      this.formPair.hidden = false;
      this.formTop5.hidden = true;
      this.modeTitle.textContent = 'How close are two timetables?';
      this.modeDesc.textContent = 'Pick two students to see their theory slots side by side. Courses without a usable slot are skipped.';
      this.randomBtnLabel.textContent = 'Random pair';
    }
  }

  setupAutocomplete(input, dropdown, clearBtn, metaEl, onEnterCallback) {
    let activeIndex = -1;

    const renderSuggestions = (query) => {
      const results = this.index.search(query, 8);
      if (results.length === 0) {
        dropdown.innerHTML = `
          <div class="suggestion-item" style="cursor: default; color: var(--text-subtle);">
            <span>No student found matching "<strong>${this.escapeHtml(query)}</strong>"</span>
          </div>`;
        dropdown.hidden = false;
        activeIndex = -1;
        return;
      }

      dropdown.innerHTML = results.map((s, idx) => {
        const highlighted = this.highlightMatch(s.name, query);
        const regBadge = s.reg_no ? `<span class="suggestion-badge">${this.escapeHtml(s.reg_no)}</span>` : '';
        return `
          <div class="suggestion-item" role="option" data-name="${this.escapeHtml(s.name)}" data-fp="${s.fingerprint}" data-idx="${idx}">
            <div class="suggestion-main">
              <span class="suggestion-name">${highlighted}</span>
              <div class="suggestion-sub">
                <span>${s.fingerprint} usable theory slots</span>
              </div>
            </div>
            ${regBadge}
          </div>
        `;
      }).join('');

      dropdown.hidden = false;
      activeIndex = -1;

      dropdown.querySelectorAll('.suggestion-item[data-name]').forEach(item => {
        item.addEventListener('click', () => {
          this.selectStudent(input, dropdown, clearBtn, metaEl, item.dataset.name, item.dataset.fp);
        });
      });
    };

    input.addEventListener('input', () => {
      const val = input.value;
      clearBtn.style.display = val ? 'block' : 'none';
      this.hideError();

      if (val.trim().length > 0) {
        const exact = this.index.findStudent(val);
        if (exact) {
          metaEl.innerHTML = `<span class="chip">${exact.fingerprint} usable theory courses</span>`;
          metaEl.hidden = false;
        } else {
          metaEl.hidden = true;
        }
        renderSuggestions(val);
      } else {
        dropdown.hidden = true;
        metaEl.hidden = true;
      }
    });

    input.addEventListener('focus', () => {
      if (input.value.trim().length > 0) {
        renderSuggestions(input.value);
      }
    });

    clearBtn.addEventListener('click', () => {
      input.value = '';
      clearBtn.style.display = 'none';
      dropdown.hidden = true;
      metaEl.hidden = true;
      this.hideError();
      input.focus();
    });

    input.addEventListener('keydown', (e) => {
      const items = dropdown.querySelectorAll('.suggestion-item[data-name]');
      if (dropdown.hidden || items.length === 0) {
        if (e.key === 'Enter') {
          e.preventDefault();
          if (onEnterCallback) onEnterCallback();
        }
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeIndex = (activeIndex + 1) % items.length;
        this.updateActiveItem(items, activeIndex);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeIndex = (activeIndex - 1 + items.length) % items.length;
        this.updateActiveItem(items, activeIndex);
      } else if (e.key === 'Enter' || e.key === 'Tab') {
        if (activeIndex >= 0 && activeIndex < items.length) {
          e.preventDefault();
          const selected = items[activeIndex];
          this.selectStudent(input, dropdown, clearBtn, metaEl, selected.dataset.name, selected.dataset.fp);
        } else {
          if (items.length > 0 && e.key === 'Enter') {
            e.preventDefault();
            this.selectStudent(input, dropdown, clearBtn, metaEl, items[0].dataset.name, items[0].dataset.fp);
          }
        }
      } else if (e.key === 'Escape') {
        this.hideDropdown(dropdown);
      }
    });
  }

  updateActiveItem(items, index) {
    items.forEach((item, idx) => {
      item.classList.toggle('active', idx === index);
      if (idx === index) {
        item.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  selectStudent(input, dropdown, clearBtn, metaEl, fullName, fingerprint) {
    input.value = fullName;
    clearBtn.style.display = 'block';
    this.hideDropdown(dropdown);
    this.hideError();

    if (fingerprint !== undefined) {
      metaEl.innerHTML = `<span class="chip">${fingerprint} usable theory courses</span>`;
      metaEl.hidden = false;
    }
  }

  hideDropdown(dropdown) {
    dropdown.hidden = true;
  }

  hideAllResults() {
    this.top5ResultsSection.hidden = true;
    this.pairResultsSection.hidden = true;
    this.emptyState.hidden = false;
  }

  showError(title, message) {
    this.errorTitle.textContent = title;
    this.errorMessage.textContent = message;
    this.errorBanner.hidden = false;
    this.errorBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  hideError() {
    this.errorBanner.hidden = true;
  }

  handleRandomClick() {
    this.hideError();
    if (this.currentMode === 'top5') {
      const student = this.index.getRandomStudent();
      if (!student) return;
      this.selectStudent(this.inputSingle, this.dropdownSingle, this.clearSingle, this.metaSingle, student.name, student.fingerprint);
      this.calculateTop5();
    } else {
      const pair = this.index.getRandomPair();
      if (!pair) return;
      this.selectStudent(this.inputA, this.dropdownA, this.clearA, this.metaA, pair[0].name, pair[0].fingerprint);
      this.selectStudent(this.inputB, this.dropdownB, this.clearB, this.metaB, pair[1].name, pair[1].fingerprint);
      this.calculatePairMatch();
    }
  }

  swapStudents() {
    this.hideError();
    const valA = this.inputA.value;
    const valB = this.inputB.value;
    const metaHtmlA = this.metaA.innerHTML;
    const metaHiddenA = this.metaA.hidden;
    const metaHtmlB = this.metaB.innerHTML;
    const metaHiddenB = this.metaB.hidden;

    this.inputA.value = valB;
    this.inputB.value = valA;
    this.clearA.style.display = valB ? 'block' : 'none';
    this.clearB.style.display = valA ? 'block' : 'none';

    this.metaA.innerHTML = metaHtmlB;
    this.metaA.hidden = metaHiddenB;
    this.metaB.innerHTML = metaHtmlA;
    this.metaB.hidden = metaHiddenA;

    if (!this.pairResultsSection.hidden) {
      this.calculatePairMatch();
    }
  }

  /* TOP 5 MATCH CALCULATION */
  async calculateTop5() {
    const raw = this.inputSingle.value.trim();
    if (!raw) {
      this.showError('Missing Student Input', 'Please select or enter a student name to find their top matches.');
      this.hideAllResults();
      return;
    }

    const student = this.index.findStudent(raw);
    if (!student) {
      this.showError(
        'Student Not Found',
        `Student "${raw}" was not found in the database. Please select a valid student from the suggestions.`
      );
      this.hideAllResults();
      return;
    }

    this.hideError();
    this.metaSingle.innerHTML = `<span class="chip">${student.fingerprint} usable theory courses</span>`;
    this.metaSingle.hidden = false;
    this.submitTop5Btn.disabled = true;
    this.submitTop5Btn.textContent = 'Searching…';

    try {
      const url = `/api/top5?student=${encodeURIComponent(student.name)}`;
      const res = await fetch(url);
      const data = await res.json();

      if (!res.ok || data.error) {
        throw new Error(data.message || 'Error occurred while finding top matches.');
      }

      this.renderTop5Results(data);
    } catch (err) {
      this.showError('Top 5 Matching Error', err.message);
      this.hideAllResults();
    } finally {
      this.submitTop5Btn.disabled = false;
      this.submitTop5Btn.textContent = 'Find best 5';
    }
  }

  renderTop5Results(data) {
    this.emptyState.hidden = true;
    this.pairResultsSection.hidden = true;
    this.top5ResultsSection.hidden = false;

    const target = data.target_student;
    this.top5TargetTitle.textContent = target.name;
    this.top5TargetSub.textContent = `${target.fingerprint} usable theory courses. Registration ${target.reg_no || 'N/A'}`;

    const matches = data.top_matches || [];
    if (matches.length === 0) {
      this.top5CardsList.innerHTML = `
        <div class="card" style="text-align: center; color: var(--text-muted); padding: 40px;">
          No compatible matches found for this student.
        </div>`;
      return;
    }

    this.top5CardsList.innerHTML = matches.map((m, idx) => {
      const rankNum = m.rank || (idx + 1);
      const pct = m.match_percentage || 0;
      let scoreColor = 'var(--success)';
      let scoreBg = 'var(--success-bg)';
      let scoreBorder = 'var(--success-border)';

      if (pct < 40) {
        scoreColor = 'var(--danger)';
        scoreBg = 'var(--danger-bg)';
        scoreBorder = 'var(--danger-border)';
      } else if (pct < 75) {
        scoreColor = 'var(--warning)';
        scoreBg = 'var(--warning-bg)';
        scoreBorder = 'var(--warning-border)';
      }

      return `
        <div class="top5-match-card" id="top5-card-${idx}">
          <div class="top5-card-main">
            <div class="rank-badge rank-${rankNum}">${rankNum}</div>
            
            <div class="top5-student-info">
              <h4 class="top5-student-name">${this.escapeHtml(m.matched_student_name)}</h4>
              <div class="top5-meta-row">
                <span><code>${this.escapeHtml(m.matched_student_reg_no || 'N/A')}</code></span>
                
                <span><strong>${m.matched_student_fingerprint}</strong> usable courses</span>
                
                <span><strong style="color: var(--success);">${m.matched_courses_count}</strong> of ${m.compared_courses_count} slots match</span>
                ${m.unavailable_courses_count > 0 ? `<span style="color: var(--text-muted);">${m.unavailable_courses_count} skipped</span>` : ''}
              </div>
            </div>

            <div class="top5-score-box">
              <span class="top5-score-val" style="color: ${scoreColor};">${this.escapeHtml(m.formatted_percentage)}</span>
              <span class="score-tag" style="background: ${scoreBg}; color: ${scoreColor}; border-color: ${scoreBorder};">
                ${pct >= 75 ? 'Strong match' : pct >= 40 ? 'Partial match' : 'Weak match'}
              </span>
            </div>
          </div>

          ${this.ribbon(m.comparisons)}
          <div class="top5-card-actions">
            <button type="button" class="btn-breakdown-toggle" data-idx="${idx}">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
              <span>Show courses</span>
            </button>

            <button type="button" class="btn-1v1-link" data-name="${this.escapeHtml(m.matched_student_name)}" data-target="${this.escapeHtml(target.name)}">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                <circle cx="8.5" cy="7" r="4"></circle>
              </svg>
              <span>Compare side by side</span>
            </button>
          </div>

          <!-- Collapsible Breakdown Panel -->
          <div class="top5-breakdown-panel" id="top5-breakdown-${idx}" hidden>
            <div class="table-responsive">
              <table class="breakdown-table">
                <thead>
                  <tr>
                    <th>Course</th>
                    <th>${this.escapeHtml(target.display_name || target.name)}</th>
                    <th>${this.escapeHtml(m.matched_student_display_name || m.matched_student_name)}</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  ${(m.comparisons || []).map(c => {
                    const isDiffProf = c.status === 'mismatched' && c.base_slot && c.other_slot && c.base_slot === c.other_slot;
                    return `
                    <tr>
                      <td><div class="course-title">${this.escapeHtml(c.course_name)}</div></td>
                      <td>
                        ${c.base_slot ? `
                          <div class="slot-badge-group">
                            <span class="slot-code-badge">${this.escapeHtml(c.base_slot)}</span>
                            <span class="timing-badge ${c.base_timing === 'Morning' ? 'timing-morning' : 'timing-evening'}">${c.base_timing}</span>
                          </div>
                          ${c.base_professor ? `<div class="prof-name"><span class="prof-label">Prof:</span> ${this.escapeHtml(c.base_professor)}</div>` : ''}
                        ` : `<span class="timing-badge timing-unavailable">${this.escapeHtml(c.base_timing || 'Not Enrolled')}</span>`}
                      </td>
                      <td>
                        ${c.other_slot ? `
                          <div class="slot-badge-group">
                            <span class="slot-code-badge">${this.escapeHtml(c.other_slot)}</span>
                            <span class="timing-badge ${c.other_timing === 'Morning' ? 'timing-morning' : c.other_timing === 'Evening' ? 'timing-evening' : 'timing-unavailable'}">${c.other_timing}</span>
                          </div>
                          ${c.other_professor ? `<div class="prof-name"><span class="prof-label">Prof:</span> ${this.escapeHtml(c.other_professor)}</div>` : ''}
                        ` : `<span class="timing-badge timing-unavailable">${this.escapeHtml(c.other_timing || 'Not Enrolled')}</span>`}
                      </td>
                      <td>
                        ${c.status === 'matched' ? '<span class="status-pill matched">Matched</span>' :
                          isDiffProf ? '<span class="status-pill diff-prof">Diff Prof</span>' :
                          c.status === 'mismatched' ? '<span class="status-pill mismatched">Different</span>' :
                          '<span class="status-pill unavailable">Skipped</span>'}
                        <div class="status-explanation">${this.escapeHtml(c.reason)}</div>
                      </td>
                    </tr>
                  `;
                  }).join('')}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      `;
    }).join('');

    // Setup breakdown accordions
    this.top5CardsList.querySelectorAll('.btn-breakdown-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = btn.dataset.idx;
        const panel = document.getElementById(`top5-breakdown-${idx}`);
        const isHidden = panel.hidden;
        panel.hidden = !isHidden;
        btn.querySelector('span').textContent = isHidden ? 'Hide courses' : 'Show courses';
      });
    });

    // Setup 1-on-1 compare triggers
    this.top5CardsList.querySelectorAll('.btn-1v1-link').forEach(btn => {
      btn.addEventListener('click', () => {
        const targetName = btn.dataset.target;
        const matchedName = btn.dataset.name;
        this.switchMode('pair');
        this.inputA.value = targetName;
        this.clearA.style.display = 'block';
        this.inputB.value = matchedName;
        this.clearB.style.display = 'block';
        this.calculatePairMatch();
      });
    });

    this.top5ResultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* 1-VS-1 PAIR MATCH CALCULATION */
  async calculatePairMatch() {
    const rawA = this.inputA.value.trim();
    const rawB = this.inputB.value.trim();

    if (!rawA || !rawB) {
      this.showError('Missing Student Input', 'Please enter both Student A and Student B.');
      this.hideAllResults();
      return;
    }

    const studentA = this.index.findStudent(rawA);
    const studentB = this.index.findStudent(rawB);

    if (!studentA && !studentB) {
      this.showError(
        'Students Not Found',
        `Neither "${rawA}" nor "${rawB}" were found in the database. Please select valid students from the suggestions.`
      );
      this.hideAllResults();
      return;
    }

    if (!studentA) {
      this.showError(
        'Student Not Found',
        `Student A "${rawA}" was not found in the database. Please select a valid student from the suggestions.`
      );
      this.hideAllResults();
      return;
    }

    if (!studentB) {
      this.showError(
        'Student Not Found',
        `Student B "${rawB}" was not found in the database. Please select a valid student from the suggestions.`
      );
      this.hideAllResults();
      return;
    }

    if (studentA.name === studentB.name) {
      this.showError(
        'Invalid Comparison',
        `Cannot compare student "${studentA.name}" with themselves. Please select two different students to compare.`
      );
      this.hideAllResults();
      return;
    }

    this.hideError();
    this.metaA.innerHTML = `<span class="chip">${studentA.fingerprint} usable theory courses</span>`;
    this.metaA.hidden = false;
    this.metaB.innerHTML = `<span class="chip">${studentB.fingerprint} usable theory courses</span>`;
    this.metaB.hidden = false;
    this.submitPairBtn.disabled = true;
    this.submitPairBtn.textContent = 'Comparing…';

    try {
      const url = `/api/match?student_a=${encodeURIComponent(studentA.name)}&student_b=${encodeURIComponent(studentB.name)}`;
      const res = await fetch(url);
      const data = await res.json();

      if (!res.ok || data.error) {
        throw new Error(data.message || 'Error occurred while comparing students.');
      }

      this.renderPairResults(data);
    } catch (err) {
      this.showError('Student Matching Error', err.message);
      this.hideAllResults();
    } finally {
      this.submitPairBtn.disabled = false;
      this.submitPairBtn.textContent = 'Compare';
    }
  }

  renderPairResults(data) {
    this.emptyState.hidden = true;
    this.top5ResultsSection.hidden = true;
    this.pairResultsSection.hidden = false;

    const matchPctEl = document.getElementById('match-percentage');
    const matchTagEl = document.getElementById('match-tag');

    if (data.has_usable_data && data.formatted_percentage !== 'N/A') {
      matchPctEl.textContent = data.formatted_percentage;
      const pctVal = data.match_percentage || 0;

      if (pctVal >= 75) {
        matchTagEl.textContent = 'High Compatibility';
        matchTagEl.style.backgroundColor = 'var(--success-bg)';
        matchTagEl.style.color = 'var(--success)';
        matchTagEl.style.borderColor = 'var(--success-border)';
      } else if (pctVal >= 40) {
        matchTagEl.textContent = 'Partial match';
        matchTagEl.style.backgroundColor = 'var(--warning-bg)';
        matchTagEl.style.color = 'var(--warning)';
        matchTagEl.style.borderColor = 'var(--warning-border)';
      } else {
        matchTagEl.textContent = 'Weak match';
        matchTagEl.style.backgroundColor = 'var(--danger-bg)';
        matchTagEl.style.color = 'var(--danger)';
        matchTagEl.style.borderColor = 'var(--danger-border)';
      }
    } else {
      matchPctEl.textContent = 'N/A';
      matchTagEl.textContent = 'No Usable Slots';
      matchTagEl.style.backgroundColor = 'rgba(148, 163, 184, 0.15)';
      matchTagEl.style.color = 'var(--text-muted)';
      matchTagEl.style.borderColor = 'var(--border-color)';
    }

    const nameA = data.student_a_name || data.base_student_name;
    const nameB = data.student_b_name || data.other_student_name;
    const fpA = data.student_a_fingerprint !== undefined ? data.student_a_fingerprint : data.base_fingerprint;
    const fpB = data.student_b_fingerprint !== undefined ? data.student_b_fingerprint : data.other_fingerprint;

    document.getElementById('base-student-name').textContent = nameA;
    document.getElementById('base-student-fp').textContent = `${fpA} usable theory courses`;

    document.getElementById('other-student-name').textContent = nameB;
    document.getElementById('other-student-fp').textContent = `${fpB} usable theory courses`;

    const labelA = document.getElementById('base-student-label');
    if (labelA) labelA.textContent = 'Student A';
    const labelB = document.getElementById('other-student-label');
    if (labelB) labelB.textContent = 'Student B';

    const thA = document.getElementById('th-student-a');
    if (thA) thA.textContent = nameA;
    const thB = document.getElementById('th-student-b');
    if (thB) thB.textContent = nameB;

    document.getElementById('adjustment-explanation').textContent = data.adjustment_explanation;

    document.getElementById('stat-matched-count').textContent = data.matched_courses_count;
    document.getElementById('stat-mismatched-count').textContent = data.mismatched_courses_count;
    document.getElementById('stat-unavailable-count').textContent = data.unavailable_courses_count;
    document.getElementById('stat-compared-count').textContent = data.compared_courses_count;

    this.currentComparisons = data.comparisons || [];
    document.getElementById('pair-ribbon').innerHTML = this.ribbon(this.currentComparisons);

    this.countAll.textContent = this.currentComparisons.length;
    this.countMatched.textContent = data.matched_courses_count;
    this.countMismatched.textContent = data.mismatched_courses_count;
    this.countUnavailable.textContent = data.unavailable_courses_count;

    this.renderPairBreakdownTable();

    const addCourses = data.other_additional_courses || [];
    if (addCourses.length > 0) {
      this.additionalWrap.hidden = false;
      this.additionalCount.textContent = addCourses.length;
      this.additionalGrid.innerHTML = addCourses.map(c => `
        <div class="additional-item">
          <div>
            <span class="additional-title">${this.escapeHtml(c.course_name)}</span>
            ${c.professor ? `<div class="prof-name"><span class="prof-label">Prof:</span> ${this.escapeHtml(c.professor)}</div>` : ''}
          </div>
          <div class="slot-badge-group">
            <span class="slot-code-badge">${this.escapeHtml(c.slot || 'N/A')}</span>
            <span class="timing-badge ${c.timing === 'Morning' ? 'timing-morning' : c.timing === 'Evening' ? 'timing-evening' : 'timing-unavailable'}">${c.timing}</span>
          </div>
        </div>
      `).join('');
    } else {
      this.additionalWrap.hidden = true;
    }

    this.pairResultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  renderPairBreakdownTable() {
    const filter = this.activeFilter;
    const filtered = this.currentComparisons.filter(c => {
      if (filter === 'all') return true;
      return c.status === filter;
    });

    if (filtered.length === 0) {
      this.breakdownTbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; padding: 32px; color: var(--text-subtle);">
            No courses in category "${this.escapeHtml(filter)}".
          </td>
        </tr>`;
      return;
    }

    this.breakdownTbody.innerHTML = filtered.map(c => {
      const baseSlotBadge = c.base_slot ? `
        <div class="slot-badge-group">
          <span class="slot-code-badge">${this.escapeHtml(c.base_slot)}</span>
          <span class="timing-badge ${c.base_timing === 'Morning' ? 'timing-morning' : 'timing-evening'}">${c.base_timing}</span>
        </div>
        ${c.base_professor ? `<div class="prof-name"><span class="prof-label">Prof:</span> ${this.escapeHtml(c.base_professor)}</div>` : ''}` : `<span class="timing-badge timing-unavailable">${this.escapeHtml(c.base_timing || 'Not Enrolled')}</span>`;

      const otherSlotBadge = c.other_slot ? `
        <div class="slot-badge-group">
          <span class="slot-code-badge">${this.escapeHtml(c.other_slot)}</span>
          <span class="timing-badge ${c.other_timing === 'Morning' ? 'timing-morning' : 'timing-evening'}">${c.other_timing}</span>
        </div>
        ${c.other_professor ? `<div class="prof-name"><span class="prof-label">Prof:</span> ${this.escapeHtml(c.other_professor)}</div>` : ''}` : `<span class="timing-badge timing-unavailable">${this.escapeHtml(c.other_timing || 'Not Enrolled')}</span>`;

      const isDiffProf = c.status === 'mismatched' && c.base_slot && c.other_slot && c.base_slot === c.other_slot;

      let statusBadge = '';
      if (c.status === 'matched') {
        statusBadge = `<span class="status-pill matched">Matched</span>`;
      } else if (isDiffProf) {
        statusBadge = `<span class="status-pill diff-prof">Diff Prof</span>`;
      } else if (c.status === 'mismatched') {
        statusBadge = `<span class="status-pill mismatched">Different</span>`;
      } else {
        statusBadge = `<span class="status-pill unavailable">Skipped</span>`;
      }

      return `
        <tr>
          <td>
            <div class="course-title">${this.escapeHtml(c.course_name)}</div>
          </td>
          <td>${baseSlotBadge}</td>
          <td>${otherSlotBadge}</td>
          <td>
            ${statusBadge}
            <div class="status-explanation">${this.escapeHtml(c.reason)}</div>
          </td>
        </tr>
      `;
    }).join('');
  }

  ribbon(list) {
    list = list || [];
    const hit = list.filter(c => c.status === 'matched').length;
    const cells = list.map((c, i) =>
      `<i class="cell ${this.escapeHtml(c.status)}" style="--i:${i}" title="${this.escapeHtml(c.course_name)}"></i>`).join('');
    return `<div class="ribbon" role="img" aria-label="${hit} of ${list.length} courses share a slot">${cells}</div>`;
  }

  highlightMatch(text, query) {
    if (!query) return this.escapeHtml(text);
    const q = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${q})`, 'gi');
    return this.escapeHtml(text).replace(regex, '<mark>$1</mark>');
  }

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}

// Start the application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window.app = new MatcherApp();
});
