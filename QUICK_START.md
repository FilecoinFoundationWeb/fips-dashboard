# Quick Start - Publishing Your Dashboard

## 🚀 Fastest Way: GitHub Pages (Recommended)

### Option A: Automated Setup (Easiest)

```bash
# Make sure you have GitHub CLI installed
# Install from: https://cli.github.com/

# Run the setup script
./setup-github-pages.sh
```

Follow the prompts, and you're done! Your dashboard will be live in minutes.

### Option B: Manual Setup

1. **Create a GitHub repository**
   - Go to https://github.com/new
   - Name it `fips-dashboard` (or any name you like)
   - Make it **Public**
   - Don't initialize with README

2. **Upload your files**
   ```bash
   cd /path/to/your/project
   git init
   git add *.html *.py *.md .github/
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/fips-dashboard.git
   git push -u origin main
   ```

3. **Enable GitHub Pages**
   - Go to your repository → Settings → Pages
   - Source: Deploy from a branch
   - Branch: `main`, Folder: `/ (root)`
   - Click Save

4. **Your dashboard is live!**
   - Main: `https://YOUR_USERNAME.github.io/fips-dashboard/fips-dashboard-static.html`
   - Timeline: `https://YOUR_USERNAME.github.io/fips-dashboard/fips-timeline-tracker.html`
   - Index: `https://YOUR_USERNAME.github.io/fips-dashboard/` (redirects to the dashboard)

## 📋 What Gets Published

- ✅ `fips-dashboard-static.html` - Main dashboard
- ✅ `fips-timeline-tracker.html` - Timeline tracker  
- ✅ `index.html` - Landing page
- ✅ Auto-updates every 6 hours via GitHub Actions

## 🔄 Auto-Update

The dashboard will automatically update every 6 hours. You can also:
- Manually trigger updates in the Actions tab
- Updates happen automatically when you push code changes

## 🌐 Other Hosting Options

### Netlify (Drag & Drop)
1. Go to https://app.netlify.com/drop
2. Drag your HTML files
3. Done! Get instant URL

### Vercel
1. Go to https://vercel.com
2. Import your GitHub repo
3. Auto-deploys on every push

### Any Web Host
Just upload the `.html` files to any web hosting service!

## 📝 Files You Need

Minimum files to publish:
- `fips-dashboard-static.html`
- `fips-timeline-tracker.html`
- `index.html` (optional, for landing page)

The Python scripts are only needed if you want to regenerate locally or use GitHub Actions for auto-updates.

## 🎯 Next Steps

1. Publish using one of the methods above
2. Share your dashboard URL
3. The dashboard auto-updates, so you're all set!

For detailed instructions, see [PUBLISHING_GUIDE.md](PUBLISHING_GUIDE.md)
