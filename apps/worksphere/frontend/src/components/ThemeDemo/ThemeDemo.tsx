import { Box, Button, Card, Grid, Paper, Stack, useTheme } from '@mui/material';
import type { WorkSphereTheme } from '../../theme';
import SoftButton from '../SoftButton';
import SoftTypography from '../SoftTypography';
import SoftBadge from '../SoftBadge';
import SoftAvatar from '../SoftAvatar';
import SoftProgress from '../SoftProgress';

const ThemeDemo = () => {
  const theme = useTheme<WorkSphereTheme>();

  const colorKeys = ['primary', 'secondary', 'info', 'success', 'warning', 'error'] as const;
  const shadowKeys = ['xs', 'sm', 'md', 'lg', 'xl'] as const;
  const borderRadiusKeys = ['xs', 'sm', 'md', 'lg', 'xl', 'xxl', 'section'] as const;
  const avatarSizes = ['xs', 'sm', 'md', 'lg', 'xl', 'xxl'] as const;

  return (
    <Stack spacing={2} alignItems="center" maxWidth={1200} mx="auto" p={2}>
      <Stack spacing={1} alignItems="center">
        <SoftTypography variant="h1" color="primary" textGradient>
          WorkSphere
        </SoftTypography>
        <SoftTypography variant="h4" color="text" opacity={0.8}>
          Theme System
        </SoftTypography>
      </Stack>

      <Grid container spacing={2}>
        {/* Typography Section */}
        <Grid item xs={12}>
          <Card sx={{ p: 2 }}>
            <SoftTypography variant="h5" color="dark" mb={2}>
              Typography
            </SoftTypography>
            <Grid container spacing={2}>
              {/* Regular Typography */}
              <Grid item xs={12} md={4}>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Regular Text Styles
                </SoftTypography>
                <Stack spacing={2}>
                  <SoftTypography variant="h1" sx={{ fontWeight: 700 }}>H1 Heading</SoftTypography>
                  <SoftTypography variant="h2" sx={{ fontWeight: 700 }}>H2 Heading</SoftTypography>
                  <SoftTypography variant="h3" sx={{ fontWeight: 600 }}>H3 Heading</SoftTypography>
                  <SoftTypography variant="h4" sx={{ fontWeight: 600 }}>H4 Heading</SoftTypography>
                  <SoftTypography variant="h5" sx={{ fontWeight: 600 }}>H5 Heading</SoftTypography>
                  <SoftTypography variant="h6" sx={{ fontWeight: 600 }}>H6 Heading</SoftTypography>
                  <SoftTypography variant="body1" sx={{ fontWeight: 400 }}>Body 1 Text</SoftTypography>
                  <SoftTypography variant="body2" sx={{ fontWeight: 400 }}>Body 2 Text</SoftTypography>
                </Stack>
              </Grid>

              {/* Gradient Typography */}
              <Grid item xs={12} md={4}>
                <SoftTypography variant="subtitle1" color="dark" mb={1}>
                  Gradient Text Styles
                </SoftTypography>
                <Stack spacing={1}>
                  {colorKeys.map((color) => (
                    <SoftTypography
                      key={color}
                      variant="h3"
                      color={color}
                      textGradient
                      fontWeight="bold"
                    >
                      {color.charAt(0).toUpperCase() + color.slice(1)} Gradient
                    </SoftTypography>
                  ))}
                </Stack>
              </Grid>

              {/* Font Weights */}
              <Grid item xs={12} md={4}>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Font Weights
                </SoftTypography>
                <Stack spacing={2}>
                  <SoftTypography variant="h4" sx={{ fontWeight: 300 }}>Light</SoftTypography>
                  <SoftTypography variant="h4" sx={{ fontWeight: 400 }}>Regular</SoftTypography>
                  <SoftTypography variant="h4" sx={{ fontWeight: 600 }}>Medium</SoftTypography>
                  <SoftTypography variant="h4" sx={{ fontWeight: 700 }}>Bold</SoftTypography>
                </Stack>
              </Grid>
            </Grid>
          </Card>
        </Grid>

        {/* Colors Section */}
        <Grid item xs={12} md={8}>
          <Card sx={{ p: 2 }}>
            <SoftTypography variant="h5" color="dark" mb={2}>
              Colors & Buttons
            </SoftTypography>
            <Stack spacing={2}>
              {/* MUI Buttons */}
              <Box>
                <SoftTypography variant="subtitle1" color="dark" mb={1}>
                  MUI Buttons
                </SoftTypography>
                <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                  {colorKeys.map((color) => (
                    <Button 
                      key={color} 
                      variant="contained" 
                      color={color}
                      className={`bg-gradient-${color} text-sm text-capitalize font-weight-bold`}
                      sx={{ 
                        fontSize: '0.75rem',
                        textTransform: 'capitalize',
                        fontWeight: 700
                      }}
                    >
                      {color}
                    </Button>
                  ))}
                </Stack>
                <Stack direction="row" spacing={1} flexWrap="wrap" gap={1} mt={2}>
                  {colorKeys.map((color) => (
                    <Button 
                      key={color} 
                      variant="outlined" 
                      color={color}
                      className="text-sm text-capitalize font-weight-bold"
                      sx={{ 
                        fontSize: '0.75rem',
                        textTransform: 'capitalize',
                        fontWeight: 700
                      }}
                    >
                      {color}
                    </Button>
                  ))}
                </Stack>
              </Box>

              {/* Soft UI Buttons */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Soft UI Buttons
                </SoftTypography>
                <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                  {colorKeys.map((color) => (
                    <SoftButton 
                      key={color} 
                      color={color} 
                      variant="gradient"
                      className={`bg-gradient-${color} text-xs text-uppercase font-weight-bold`}
                      sx={{ 
                        fontSize: '0.75rem',
                        textTransform: 'capitalize',
                        fontWeight: 700
                      }}
                    >
                      {color}
                    </SoftButton>
                  ))}
                </Stack>
                <Stack direction="row" spacing={1} flexWrap="wrap" gap={1} mt={2}>
                  {colorKeys.map((color) => (
                    <SoftButton 
                      key={color} 
                      color={color} 
                      variant="outlined"
                      className="text-xs text-uppercase font-weight-bold"
                      sx={{ 
                        fontSize: '0.75rem',
                        textTransform: 'capitalize',
                        fontWeight: 700
                      }}
                    >
                      {color}
                    </SoftButton>
                  ))}
                </Stack>
              </Box>
            </Stack>
          </Card>
        </Grid>

        {/* Badges Section */}
        <Grid item xs={12}>
          <Card sx={{ p: 2 }}>
            <SoftTypography variant="h5" color="dark" mb={2}>
              Badges
            </SoftTypography>
            <Stack spacing={3}>
              {/* Contained Badges */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Contained Badges
                </SoftTypography>
                <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                  {colorKeys.map((color) => (
                    <Box key={color}>
                      <SoftBadge
                        variant="contained"
                        color={color}
                        badgeContent={color}
                        sx={{ 
                          '& .MuiBadge-badge': {
                            fontSize: '0.75rem',
                            textTransform: 'uppercase',
                            fontWeight: 700
                          }
                        }}
                      >
                        <Box sx={{ width: 30, height: 30, bgcolor: 'transparent' }} />
                      </SoftBadge>
                    </Box>
                  ))}
                </Stack>
              </Box>

              {/* Gradient Badges */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Gradient Badges
                </SoftTypography>
                <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                  {colorKeys.map((color) => (
                    <Box key={color}>
                      <SoftBadge
                        variant="gradient"
                        color={color}
                        badgeContent={color}
                        sx={{ 
                          '& .MuiBadge-badge': {
                            fontSize: '0.75rem',
                            textTransform: 'uppercase',
                            fontWeight: 700
                          }
                        }}
                      >
                        <Box sx={{ width: 30, height: 30, bgcolor: 'transparent' }} />
                      </SoftBadge>
                    </Box>
                  ))}
                </Stack>
              </Box>

              {/* Outlined Badges */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Outlined Badges
                </SoftTypography>
                <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                  {colorKeys.map((color) => (
                    <Box key={color}>
                      <SoftBadge
                        variant="outlined"
                        color={color}
                        badgeContent={color}
                        sx={{ 
                          '& .MuiBadge-badge': {
                            fontSize: '0.75rem',
                            textTransform: 'uppercase',
                            fontWeight: 700
                          }
                        }}
                      >
                        <Box sx={{ width: 30, height: 30, bgcolor: 'transparent' }} />
                      </SoftBadge>
                    </Box>
                  ))}
                </Stack>
              </Box>

              {/* Status Badges */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Status Badges
                </SoftTypography>
                <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                  <Box>
                    <SoftBadge
                      variant="contained"
                      color="success"
                      badgeContent="Active"
                      sx={{ 
                        '& .MuiBadge-badge': {
                          fontSize: '0.75rem',
                          textTransform: 'uppercase',
                          fontWeight: 700
                        }
                      }}
                    >
                      <Box sx={{ width: 30, height: 30, bgcolor: 'transparent' }} />
                    </SoftBadge>
                  </Box>
                  <Box>
                    <SoftBadge
                      variant="contained"
                      color="error"
                      badgeContent="Inactive"
                      sx={{ 
                        '& .MuiBadge-badge': {
                          fontSize: '0.75rem',
                          textTransform: 'uppercase',
                          fontWeight: 700
                        }
                      }}
                    >
                      <Box sx={{ width: 30, height: 30, bgcolor: 'transparent' }} />
                    </SoftBadge>
                  </Box>
                  <Box>
                    <SoftBadge
                      variant="contained"
                      color="warning"
                      badgeContent="Pending"
                      sx={{ 
                        '& .MuiBadge-badge': {
                          fontSize: '0.75rem',
                          textTransform: 'uppercase',
                          fontWeight: 700
                        }
                      }}
                    >
                      <Box sx={{ width: 30, height: 30, bgcolor: 'transparent' }} />
                    </SoftBadge>
                  </Box>
                  <Box>
                    <SoftBadge
                      variant="contained"
                      color="info"
                      badgeContent="Processing"
                      sx={{ 
                        '& .MuiBadge-badge': {
                          fontSize: '0.75rem',
                          textTransform: 'uppercase',
                          fontWeight: 700
                        }
                      }}
                    >
                      <Box sx={{ width: 30, height: 30, bgcolor: 'transparent' }} />
                    </SoftBadge>
                  </Box>
                </Stack>
              </Box>
            </Stack>
          </Card>
        </Grid>

        {/* Shadows Section */}
        <Grid item xs={12} md={4}>
          <Card sx={{ p: 2, height: '100%' }}>
            <SoftTypography variant="h5" color="dark" mb={2}>
              Shadows
            </SoftTypography>
            <Stack spacing={2}>
              {shadowKeys.map((shadow) => (
                <Paper
                  key={shadow}
                  sx={{
                    p: 1,
                    textAlign: 'center',
                    boxShadow: theme.boxShadows[shadow],
                  }}
                >
                  {shadow}
                </Paper>
              ))}
            </Stack>
          </Card>
        </Grid>

        {/* Border Radius Section */}
        <Grid item xs={12}>
          <Card sx={{ p: 2 }}>
            <SoftTypography variant="h5" color="dark" mb={2}>
              Border Radius
            </SoftTypography>
            <Grid container spacing={1}>
              {colorKeys.map((color, index) => (
                borderRadiusKeys.map((key) => (
                  <Grid item xs={6} sm={4} md={3} key={`${color}-${key}`}>
                    <Box
                      sx={{
                        bgcolor: theme.palette[color].main,
                        borderRadius: theme.borders.borderRadius[key],
                        p: 1,
                        textAlign: 'center',
                        color: theme.palette[color].contrastText,
                      }}
                    >
                      {key}
                    </Box>
                  </Grid>
                ))
              ))[0]}
            </Grid>
          </Card>
        </Grid>

        {/* Gradients Section */}
        <Grid item xs={12}>
          <Card sx={{ p: 2 }}>
            <SoftTypography variant="h5" color="dark" mb={2}>
              Helper Functions
            </SoftTypography>
            <Grid container spacing={1}>
              <Grid item xs={12} md={6}>
                <Paper sx={{ p: 2 }}>
                  <SoftTypography variant="subtitle1" color="dark" mb={1}>
                    Linear Gradient
                  </SoftTypography>
                  <Box
                    sx={{
                      height: 80,
                      background: theme.functions.linearGradient(
                        '45deg',
                        theme.palette.primary.main,
                        theme.palette.secondary.main
                      ),
                      borderRadius: theme.borders.borderRadius.md,
                    }}
                  />
                </Paper>
              </Grid>
              <Grid item xs={12} md={6}>
                <Paper sx={{ p: 2 }}>
                  <SoftTypography variant="subtitle1" color="dark" mb={1}>
                    RGBA Color
                  </SoftTypography>
                  <Box
                    sx={{
                      height: 80,
                      background: theme.functions.rgba(theme.palette.primary.main, 0.5),
                      borderRadius: theme.borders.borderRadius.md,
                    }}
                  />
                </Paper>
              </Grid>
            </Grid>
          </Card>
        </Grid>

        {/* Avatars Section */}
        <Grid item xs={12}>
          <Card sx={{ p: 2 }}>
            <SoftTypography variant="h5" color="dark" mb={2}>
              Avatars
            </SoftTypography>
            <Stack spacing={3}>
              {/* Regular Avatars */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Regular Avatars
                </SoftTypography>
                <Stack direction="row" spacing={2} alignItems="center">
                  {avatarSizes.map((size, index) => (
                    <SoftAvatar
                      key={size}
                      size={size}
                      bgColor={colorKeys[index % colorKeys.length]}
                      sx={{ 
                        background: theme.palette[colorKeys[index % colorKeys.length]].main,
                        color: theme.palette.white.main
                      }}
                    >
                      {size.toUpperCase()}
                    </SoftAvatar>
                  ))}
                </Stack>
              </Box>

              {/* Gradient Avatars */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Gradient Avatars
                </SoftTypography>
                <Stack direction="row" spacing={2} alignItems="center">
                  {colorKeys.map((color) => (
                    <SoftAvatar
                      key={color}
                      size="md"
                      variant="gradient"
                      bgColor={color}
                      sx={{ 
                        background: theme.functions.linearGradient(
                          'to right',
                          theme.palette.gradients[color].main,
                          theme.palette.gradients[color].state
                        ),
                        color: theme.palette.white.main
                      }}
                    >
                      {color.charAt(0).toUpperCase()}
                    </SoftAvatar>
                  ))}
                </Stack>
              </Box>

              {/* Shadow Avatars */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Shadow Avatars
                </SoftTypography>
                <Stack direction="row" spacing={4} alignItems="center" sx={{ p: 3 }}>
                  {shadowKeys.map((shadow, index) => (
                    <Box
                      key={shadow}
                      sx={{
                        boxShadow: theme.boxShadows[shadow],
                        borderRadius: '50%',
                        p: 0.5,
                      }}
                    >
                      <SoftAvatar
                        size={avatarSizes[index % avatarSizes.length]}
                        variant="gradient"
                        bgColor={colorKeys[index % colorKeys.length]}
                        sx={{ 
                          background: theme.functions.linearGradient(
                            'to right',
                            theme.palette.gradients[colorKeys[index % colorKeys.length]].main,
                            theme.palette.gradients[colorKeys[index % colorKeys.length]].state
                          ),
                          color: theme.palette.white.main
                        }}
                      >
                        {shadow.toUpperCase()}
                      </SoftAvatar>
                    </Box>
                  ))}
                </Stack>
              </Box>

              {/* With Content */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  With Content
                </SoftTypography>
                <Stack direction="row" spacing={2} alignItems="center">
                  <SoftAvatar size="md" variant="gradient" bgColor="primary" sx={{ 
                    background: theme.functions.linearGradient(
                      'to right',
                      theme.palette.gradients.primary.main,
                      theme.palette.gradients.primary.state
                    ),
                    color: theme.palette.white.main 
                  }}>VS</SoftAvatar>
                  <SoftAvatar size="md" variant="gradient" bgColor="secondary" sx={{ 
                    background: theme.functions.linearGradient(
                      'to right',
                      theme.palette.gradients.secondary.main,
                      theme.palette.gradients.secondary.state
                    ),
                    color: theme.palette.white.main 
                  }}>JD</SoftAvatar>
                  <SoftAvatar size="md" variant="gradient" bgColor="info" sx={{ 
                    background: theme.functions.linearGradient(
                      'to right',
                      theme.palette.gradients.info.main,
                      theme.palette.gradients.info.state
                    ),
                    color: theme.palette.white.main 
                  }}>+3</SoftAvatar>
                  <SoftAvatar size="md" variant="gradient" bgColor="success" sx={{ 
                    background: theme.functions.linearGradient(
                      'to right',
                      theme.palette.gradients.success.main,
                      theme.palette.gradients.success.state
                    ),
                    color: theme.palette.white.main 
                  }}>
                    <i className="fas fa-user" />
                  </SoftAvatar>
                  <SoftAvatar size="md" variant="gradient" bgColor="warning" sx={{ 
                    background: theme.functions.linearGradient(
                      'to right',
                      theme.palette.gradients.warning.main,
                      theme.palette.gradients.warning.state
                    ),
                    color: theme.palette.white.main 
                  }}>
                    <i className="fas fa-cog" />
                  </SoftAvatar>
                  <SoftAvatar size="md" variant="gradient" bgColor="error" sx={{ 
                    background: theme.functions.linearGradient(
                      'to right',
                      theme.palette.gradients.error.main,
                      theme.palette.gradients.error.state
                    ),
                    color: theme.palette.white.main 
                  }}>
                    <i className="fas fa-bell" />
                  </SoftAvatar>
                </Stack>
              </Box>
            </Stack>
          </Card>
        </Grid>

        {/* Progress Section */}
        <Grid item xs={12}>
          <Card sx={{ p: 2 }}>
            <SoftTypography variant="h5" color="dark" mb={2}>
              Progress Bars
            </SoftTypography>
            <Stack spacing={3}>
              {/* Regular Progress */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Regular Progress
                </SoftTypography>
                <Stack spacing={2}>
                  {colorKeys.map((color, index) => (
                    <Box key={color}>
                      <SoftTypography variant="button" color={color} fontWeight="medium" mb={1}>
                        {color.charAt(0).toUpperCase() + color.slice(1)} Progress
                      </SoftTypography>
                      <SoftProgress
                        variant="contained"
                        color={color}
                        value={30 + index * 10}
                        sx={{
                          height: 6,
                          borderRadius: theme.borders.borderRadius.lg,
                          background: theme.functions.rgba(theme.palette[color].main, 0.1),
                        }}
                      />
                    </Box>
                  ))}
                </Stack>
              </Box>

              {/* Gradient Progress */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Gradient Progress
                </SoftTypography>
                <Stack spacing={2}>
                  {colorKeys.map((color, index) => (
                    <Box key={color}>
                      <SoftTypography variant="button" color={color} fontWeight="medium" mb={1}>
                        {color.charAt(0).toUpperCase() + color.slice(1)} Gradient
                      </SoftTypography>
                      <SoftProgress
                        variant="gradient"
                        color={color}
                        value={85 - index * 10}
                        sx={{
                          height: 10,
                          borderRadius: theme.borders.borderRadius.xl,
                          background: theme.functions.rgba(theme.palette[color].main, 0.1),
                          "& .MuiLinearProgress-bar": {
                            background: theme.functions.linearGradient(
                              'to right',
                              theme.palette.gradients[color].main,
                              theme.palette.gradients[color].state
                            ),
                            borderRadius: theme.borders.borderRadius.xl,
                          }
                        }}
                      />
                    </Box>
                  ))}
                </Stack>
              </Box>

              {/* Progress with Labels */}
              <Box>
                <SoftTypography variant="body2" color="dark" sx={{ mb: 2, fontWeight: 'bold', opacity: 0.7 }}>
                  Progress with Labels
                </SoftTypography>
                <Stack spacing={3}>
                  {colorKeys.map((color, index) => {
                    const value = (index + 1) * 15;
                    return (
                      <Box key={color}>
                        <Stack direction="row" justifyContent="space-between" mb={1}>
                          <SoftTypography variant="button" color={color} fontWeight="medium">
                            {color.charAt(0).toUpperCase() + color.slice(1)}
                          </SoftTypography>
                          <SoftTypography variant="button" color={color} fontWeight="medium">
                            {value}%
                          </SoftTypography>
                        </Stack>
                        <SoftProgress
                          variant="gradient"
                          color={color}
                          value={value}
                          sx={{
                            height: 8,
                            borderRadius: theme.borders.borderRadius.md,
                            background: theme.functions.rgba(theme.palette[color].main, 0.1),
                            boxShadow: theme.boxShadows.xs,
                            "& .MuiLinearProgress-bar": {
                              background: theme.functions.linearGradient(
                                'to right',
                                theme.palette.gradients[color].main,
                                theme.palette.gradients[color].state
                              ),
                              borderRadius: theme.borders.borderRadius.md,
                            }
                          }}
                        />
                      </Box>
                    );
                  })}
                </Stack>
              </Box>
            </Stack>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default ThemeDemo;
