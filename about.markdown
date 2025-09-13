---
layout: default
title: About
---

<div class="page-container">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ page.title }}</title>

  <!-- Default CSS -->
  <link rel="stylesheet" href="{{ '/assets/css/about.css' | relative_url }}">

  <!-- Include additional CSS if set in the page's front matter -->
  {% if page.extra_css %}
    <link rel="stylesheet" href="{{ page.extra_css | relative_url }}">
  {% endif %}

</head>
    <main class="about-container">
        <section class="profile-section">
            <img src="{{ '/assets/images/pfp.png' | relative_url }}" alt="Drew Alleman" class="profile-image">
            <div class="profile-info">
                <h1 class="section-title">Drew Alleman</h1>
                <div class="social-links">
                    <a href="https://www.youtube.com/@drewalleman" class="social-link">YouTube</a>
                    <a href="https://github.com/Drew-Alleman" class="social-link">GitHub</a>
                    <a href="https://www.linkedin.com/in/drew-alleman-909352209" class="social-link">LinkedIn</a>
                    <a href="mailto:contact@drewalleman.xyz" class="social-link">Email</a>
                </div>
            </div>
        </section>
        <section class="content-section">
            <h2 class="section-title">About Me</h2>
            <p>Hi, I’m Drew. I’m passionate about both creating and breaking software, always exploring new technologies and pushing my skills further. I believe strongly in open-source and the value of sharing knowledge with the community. Most of my tools and projects are freely available on GitHub for others to use, learn from, and build upon.</p>
        </section>
        <section class="content-section">
            <h2 class="section-title">Technical Skills</h2>
            <div class="skill-grid">
                <div class="skill-item">Security Testing & Auditing</div>
                <div class="skill-item">Penetration Testing</div>
                <div class="skill-item">Malware Analysis</div>
                <div class="skill-item">Network Security</div>
                <div class="skill-item">Python</div>
                <div class="skill-item">Powershell</div>
                <div class="skill-item">C++ and C#</div>
            </div>
        </section>

        <section class="content-section">
            <h2 class="section-title">Certifications & Achievements</h2>
            <ul class="certification-list">
                <li class="certification-item">
                    <strong>Offsec OSCP+</strong>
                    <div class="text-sm text-gray-400">2025</div>
                </li>
                <li class="certification-item">
                    <strong>PenTest+ PT0-002</strong> - CompTIA
                    <div class="text-sm text-gray-400">2023</div>
                </li>
                <li class="certification-item">
                    <strong>Security+</strong> - CompTIA
                    <div class="text-sm text-gray-400">2021</div>
                </li>
            </ul>
        </section>

        <section class="content-section">
            <h2 class="section-title">Recent Projects</h2>
            <div class="project-list">
                <div class="certification-item">
                    <h3>DataSurgeon</h3>
                    <p>Quickly Extracts IP's, Email Addresses, Hashes, Files, Credit Cards, Social Security Numbers and a lot More From Text</p>
                    <a href="https://github.com/Drew-Alleman/DataSurgeon" class="social-link">View Project</a>
                </div>
                <div class="certification-item">
                    <h3>Netstat Trojan</h3>
                    <p>Reverse-TCP backdoor disguised within the netstat utility. It's designed to automatically exclude itself from the netstat output.</p>
                    <a href="https://github.com/Drew-Alleman/netstat-trojan" class="social-link">View Project</a>
                </div>
            </div>
        </section>
    </main>
</div>
