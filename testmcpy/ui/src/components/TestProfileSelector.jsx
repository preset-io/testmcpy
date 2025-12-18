import React, { useState, useEffect } from 'react';
import { LoadingSpinner } from './LoadingSpinner';
import ErrorAlert from './ErrorAlert';

export const TestProfileSelector = ({ onProfileChange, currentProfile }) => {
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
      const response = await fetch('/api/test/profiles');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: Failed to load test profiles`);
      }

      const data = await response.json();
      setProfiles(data.profiles || []);
      setDefaultProfile(data.default);

      // Notify parent if we have a default and no current selection
      if (data.default && !currentProfile && onProfileChange) {
        onProfileChange(data.default);
      }
    } catch (err) {
      console.error('Error loading test profiles:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const setDefault = async (profileId) => {
    try {
      const response = await fetch(`/api/test/profiles/default/${profileId}`, {
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
        <LoadingSpinner size="md" text="Loading test profiles..." />
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
          <h3>No Test Profiles</h3>
          <p>
            Create a <code>.test_profiles.yaml</code> file to configure test profiles.
          </p>
          <p className="text-sm text-muted">
            Example: <code>cp .test_profiles.yaml.example .test_profiles.yaml</code>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="profile-selector">
      <div className="profile-selector-header">
        <h3>Test Profiles</h3>
        <button onClick={loadProfiles} className="btn-refresh" title="Refresh">
          🔄
        </button>
      </div>

      <div className="profile-list">
        {profiles.map((profile) => {
          const isDefault = profile.profile_id === defaultProfile;
          const isCurrent = profile.profile_id === currentProfile;
          const defaultConfig = profile.test_configs.find(c => c.default) || profile.test_configs[0];

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
                  <span className="detail-label">Test Configs:</span>
                  <span className="detail-value">{profile.test_configs.length}</span>
                </div>
                {defaultConfig && (
                  <>
                    <div className="detail-item">
                      <span className="detail-label">Tests Dir:</span>
                      <span className="detail-value">{defaultConfig.tests_dir}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Timeout:</span>
                      <span className="detail-value">{defaultConfig.timeout}s</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Parallel:</span>
                      <span className={`badge ${defaultConfig.parallel ? 'badge-success' : 'badge-secondary'}`}>
                        {defaultConfig.parallel ? 'Yes' : 'No'}
                      </span>
                    </div>
                  </>
                )}
              </div>

              {/* Show all test configs */}
              {profile.test_configs.length > 0 && (
                <div className="configs-list">
                  {profile.test_configs.map((config, idx) => (
                    <div key={idx} className="config-item">
                      <div className="config-header">
                        <span className="config-name">
                          {config.default ? '▸ ' : '  '}
                          {config.name}
                        </span>
                        <span className="config-dir text-sm text-muted">
                          {config.tests_dir}
                        </span>
                      </div>
                      {config.evaluators.length > 0 && (
                        <div className="config-evaluators">
                          <span className="text-xs text-muted">Evaluators: </span>
                          {config.evaluators.slice(0, 3).map((evaluator, i) => (
                            <span key={i} className="evaluator-badge">
                              {evaluator}
                            </span>
                          ))}
                          {config.evaluators.length > 3 && (
                            <span className="text-xs text-muted">
                              +{config.evaluators.length - 3} more
                            </span>
                          )}
                        </div>
                      )}
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
