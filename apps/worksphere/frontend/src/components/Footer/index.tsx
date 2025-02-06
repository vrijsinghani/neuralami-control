import { FC } from 'react';
import { Link } from 'react-router-dom';

// @mui material components
import { Container, Grid } from '@mui/material';

// Custom components
import SoftBox from '../SoftBox';
import SoftTypography from '../SoftTypography';

const Footer: FC = () => {
  return (
    <SoftBox component="footer" py={6}>
      <Container>
        <Grid container spacing={3}>
          <Grid item xs={12} lg={8} sx={{ textAlign: { xs: "center", lg: "left" } }}>
            <SoftBox>
              <SoftTypography variant="h6" textTransform="uppercase" mb={2}>
                WorkSphere
              </SoftTypography>
            </SoftBox>
            <SoftBox>
              <SoftTypography variant="button" fontWeight="regular" color="text">
                Copyright &copy; {new Date().getFullYear()}{" "}
                <SoftTypography
                  component={Link}
                  to="/"
                  variant="button"
                  fontWeight="regular"
                >
                  WorkSphere
                </SoftTypography>
              </SoftTypography>
            </SoftBox>
          </Grid>
          <Grid item xs={12} lg={4}>
            <SoftBox display="flex" justifyContent={{ xs: "center", lg: "flex-end" }} gap={2}>
              <SoftTypography
                component={Link}
                to="/about"
                variant="button"
                color="text"
                fontWeight="regular"
              >
                About Us
              </SoftTypography>
              <SoftTypography
                component={Link}
                to="/contact"
                variant="button"
                color="text"
                fontWeight="regular"
              >
                Contact
              </SoftTypography>
              <SoftTypography
                component={Link}
                to="/privacy"
                variant="button"
                color="text"
                fontWeight="regular"
              >
                Privacy
              </SoftTypography>
            </SoftBox>
          </Grid>
        </Grid>
      </Container>
    </SoftBox>
  );
};

export default Footer; 