import React, { useState, useEffect } from 'react';
import { LoadingSpinner } from './LoadingSpinner';
import ErrorAlert from './ErrorAlert';

export const LLMProfileSelector = ({ onProfileChange, currentProfile }) => {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [defaultProfile, setDefaultProfile] = useState(null);

  useEffect(() => {
    loadProfiles();
  }, []);

  const loadProfiles = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch('/api/llm/profiles');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: Failed to load LLM profiles`);
      }

      const data = await response.json();
      setProfiles(data.profiles || []);
      setDefaultProfile(data.default);

      // Notify parent if we have a default and no current selection
      if (data.default && !currentProfile && onProfileChange) {
        onProfileChange(data.default);
      }
    } catch (err) {
      console.error('Error loading LLM profiles:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const setDefault = async (profileId) => {
    try {
      const response = await fetch(`/api/llm/profiles/default/${profileId}`, {
        method: 'PUT',
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to set default profile');
      }

      setDefaultProfile(profileId);
      await loadProfiles();

      if (onProfileChange) {
        onProfileChange(profileId);
      }
    } catch (err) {
      console.error('Error setting default profile:', err);
      setError(err.message);
    }
  };

  if (loading) {
    return (
      <div className="profile-selector">
        <LoadingSpinner size="md" text="Loading LLM profiles..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="profile-selector">
        <ErrorAlert message={error} onRetry={loadProfiles} />
      </div>
    );
  }

  if (profiles.length === 0) {
    return (
      <div className="profile-selector">
        <div className="empty-state">
          <h3>No LLM Provider Profiles</h3>
          <p>
            Create a <code>.llm_providers.yaml</code> file to configure LLM provider profiles.
          </p>
          <p className="text-sm text-muted">
            Example: <code>cp .llm_providers.yaml.example .llm_providers.yaml</code>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="profile-selector">
      <div className="profile-selector-header">
        <h3>LLM Provider Profiles</h3>
        <button onClick={loadProfiles} className="btn-refresh" title="Refresh">
          🔄
        </button>
      </div>

      <div className="profile-list">
        {profiles.map((profile) => {
          const isDefault = profile.profile_id === defaultProfile;
          const isCurrent = profile.profile_id === currentProfile;
          const defaultProvider = profile.providers.find(p => p.default) || profile.providers[0];

          return (
            <div
              key={profile.profile_id}
              className={`profile-card ${isDefault ? 'default' : ''} ${isCurrent ? 'current' : ''}`}
              onClick={() => setDefault(profile.profile_id)}
              role="button"
              tabIndex={0}
              onKeyPress={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  setDefault(profile.profile_id);
                }
              }}
            >
              <div className="profile-header">
                <div className="profile-status">
                  {isDefault ? '●' : '○'}
                </div>
                <div className="profile-info">
                  <div className="profile-name">{profile.name}</div>
                  <div className="profile-id">{profile.profile_id}</div>
                </div>
              </div>

              {profile.description && (
                <div className="profile-description">{profile.description}</div>
              )}

              <div className="profile-details">
                <div className="detail-item">
                  <span className="detail-label">Providers:</span>
                  <span className="detail-value">{profile.providers.length}</span>
                </div>
                {defaultProvider && (
                  <>
                    <div className="detail-item">
                      <span className="detail-label">Default Model:</span>
                      <span className="detail-value">{defaultProvider.model}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Provider:</span>
                      <span className="detail-value badge">{defaultProvider.provider}</span>
                    </div>
                  </>
                )}
              </div>

              {/* Show all providers */}
              {profile.providers.length > 0 && (
                <div className="providers-list">
                  {profile.providers.map((provider, idx) => (
                    <div key={idx} className="provider-item">
                      <span className="provider-name">
                        {provider.default ? '▸ ' : '  '}
                        {provider.name}
                      </span>
                      <span className="provider-model text-sm text-muted">
                        {provider.model}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="profile-selector-footer">
        <p className="text-sm text-muted">
          Click a profile to set it as default. Default profile is marked with ●
        </p>
      </div>
    </div>
  );
};
