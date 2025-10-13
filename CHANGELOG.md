# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2024-01-XX

### Added
- **System check on startup** to validate configuration automatically
- **Settings page** (`/settings`) for updating common configuration values without editing .env files
- **Multiple Navidrome libraries support** with automatic detection and fallback handling
- **NAVIDROME_LIBRARY_ID** environment variable for targeting specific libraries
- **Enhanced Docker networking guidance** in documentation and error messages
- **Comprehensive health check system** with detailed status reporting and suggestions

### Fixed
- **Better error handling** for Navidrome multiple libraries scenarios
- **Improved 503 error resolution** when getArtists endpoint fails due to library configuration
- **Enhanced error messages** with actionable suggestions for common Docker networking issues

### Improved
- **User experience** with automatic configuration validation and clear error guidance
- **Docker networking troubleshooting** documentation with specific examples
- **API error logging** with detailed request/response information for easier debugging
- **Settings management** with UI-based updates for non-secret configuration values

### Documentation
- **Comprehensive README updates** with troubleshooting sections
- **Environment variables documentation** with Settings UI availability indicators
- **Docker networking best practices** and common issue resolution guides
- **Multiple libraries setup instructions** and configuration options

## [0.1.0] - Previous Release

### Added
- Initial release with core playlist generation functionality
- Navidrome integration
- AI-powered playlist curation
- Recipe-based playlist management
- Rediscover Weekly feature